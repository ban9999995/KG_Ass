from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from pymilvus import AnnSearchRequest

from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import HYBRID_SEARCH_LIMIT_NUMBER, HYBRID_SEARCH_RANKER_WEIGHTS
from app.shared.runtime.logger import logger, step_log
from app.infra.model.model_providers import model_provider
from app.infra.milvus.VectorStore import milvus_gateway
from app.rag.knowledge.knowledge_unit_service import filter_active_chunks
from app.shared.runtime.load_prompt import load_prompt

#1. 获取并校验参数  rewritten_query   item_names
@step_log("get_data_and_validate")
def get_data_and_validate(state) -> tuple[str,list]:
    # 1.1 获取相关参数
    rewritten_query:str  = state.get("rewritten_query")
    item_names:list[str] = state.get("item_names")
    # 1.2 非空校验和空处理
    if not rewritten_query or not item_names:
        logger.error(f"rewritten_query或者item_names为空,业务无法继续,提前终止!!")
        raise ValueError(f"rewritten_query或者item_names为空,业务无法继续,提前终止!!")
    # 1.3 返回参数
    return rewritten_query,item_names

# 2. 重写问题以及item_names作为条件进行向量搜索(chunks)
@step_log("search_chunks_by_rewritten")
def search_chunks_by_rewritten(rewritten_query,item_names,model_answer) -> list[dict]:
    #[{chunk_id/id:主键,distance:分数,entity:{}},{}]
    # 2.0 rewritten_query进行向量化处理
    result = model_provider.create_embeddings([rewritten_query + "\n" + model_answer])
    dense_vector  = result["dense"][0]
    sparse_vector = result["sparse"][0]
    # 2.1 创建requests列表 AnnSearchRequest -> expr = "item_name in item_names" || search(filter="")
    requests:list[AnnSearchRequest] =  milvus_gateway.create_requests(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        expr=f"item_name in {item_names}",  # item_names  : list[str]  = "['a','b']"
        limit=HYBRID_SEARCH_LIMIT_NUMBER * 2
    )
    # 2.2 调用封装好的混合检索函数
    response = milvus_gateway.hybrid_search(
        collection_name=milvus_gateway.chunk_collection_name,
        reqs=requests,
        ranker_weights=HYBRID_SEARCH_RANKER_WEIGHTS,
        norm_score=True,
        limit=HYBRID_SEARCH_LIMIT_NUMBER,
        output_fields=[
            "chunk_id" , "file_title" ,"parent_title","title","part","item_name","content","knowledge_unit_id","knowledge_status"
        ]
    )
    # [  [ { id/chunk_id:x,distance:分,entity:{chunk_id" , "file_title" ,"parent_title","title","part","item_name","content"}  } ] ]
    # 2.3 返回结果
    logger.info(f"问题:{rewritten_query},检索到了:{len(response[0])},结果为:{response[0]}")
    return response[0]

# 3. 优化和处理查询后的数据
# [{chunk_id/id:主键,distance:分数,entity:{}},{}] -> [{chunk_id:x,title,file_title,parent_title,content,score,type:milvus}]
@step_log("normalize_retrieved_chunk")
def normalize_retrieved_chunk(milvus_response:list[dict])->list[dict]:
    # 列表推导式
    normalize_chunks:list[dict] = [
        {
            "chunk_id":item.get("id") or item.get("chunk_id"),
            "file_title": item.get("entity",{}).get("file_title"),
            "parent_title": item.get("entity",{}).get("parent_title"),
            "title": item.get("entity",{}).get("title"),
            "part": item.get("entity",{}).get("part"),
            "item_name": item.get("entity",{}).get("item_name"),
            "knowledge_unit_id": item.get("entity",{}).get("knowledge_unit_id"),
            "knowledge_status": item.get("entity",{}).get("knowledge_status"),
            "content": item.get("entity",{}).get("content"),
            "score":item.get("distance",0.0),
            "type":"milvus" # 拼接提示词的时候告诉模型,我们数据来自于哪
        }  for item  in milvus_response
    ]
    return normalize_chunks

@step_log("call_model_create_answer")
def call_model_create_answer(rewritten_query):
    # 1.获取大语言模型对象 (非json)
    llm_model = model_provider.llm_model()
    # 2.拼接提示词 [加载文本/Message]
    hype_prompt:str = load_prompt("hyde_prompt",rewritten_query=rewritten_query)
    messages = [
        HumanMessage(content=hype_prompt)
    ]
    # 3.封装调用链
    chains = llm_model | StrOutputParser()
    # 4.模型调用
    model_answer:str = chains.invoke(messages)
    # 5.结果返回
    logger.info(f"基于:{rewritten_query}问题,模型给与的假设性回答:{model_answer}")
    return model_answer


@step_log("search_by_hyde")
def search_by_hyde(state: QueryGraphState) -> QueryGraphState:
    # 1. 获取并校验参数
    rewritten_query,item_names = get_data_and_validate(state)
    # 2. 调用模型生成假设性答案
    model_answer:str = call_model_create_answer(rewritten_query)
    # 2. 向量数据库检索chunk
    milvus_response = search_chunks_by_rewritten(rewritten_query,item_names,model_answer)
    # 3. 格式化处理
    normalize_chunks = filter_active_chunks(normalize_retrieved_chunk(milvus_response), state.get("user_context"))
    # 4. 更新state
    state['hyde_embedding_chunks'] = normalize_chunks
    return state
