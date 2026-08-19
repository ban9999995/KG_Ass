from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import HYBRID_SEARCH_LIMIT_NUMBER
from app.shared.runtime.logger import logger, step_log

@step_log("validate_and_get_data")
def validate_and_get_data(state):
    """
      获取核心参数并且校验
    :param state:
    :return:
    """
    #1. 获取参数
    embedding_chunks = state.get("embedding_chunks")
    hyde_embedding_chunks = state.get("hyde_embedding_chunks")
    #2. 非空校验
    if (not embedding_chunks) or (not hyde_embedding_chunks):
        logger.error(f"embedding_chunks或者hyde_embedding_chunks为空,业务无法继续,提前终止!")
        raise ValueError(f"embedding_chunks或者hyde_embedding_chunks为空,业务无法继续,提前终止!")
    #3. 返回结果
    return embedding_chunks,hyde_embedding_chunks

@step_log("use_rrf_rank")
def reciprocal_rank_fusion(data_list,k:int=60):
    # 记录得分[最终得分]! 做累加! 第二次获取第一次的分! 存分的时候,有一个统一的标识 chunk_id
    score_dict:dict[str,float] = {}
    chunk_dict:dict[str,dict]  = {}  # 两路chunk基本属性一定一致! 除了score chunk_id,content
    # chunks => [{chunk_id,content,...,score:milvus相似度的分,type:milvus},{chunk_id,content,...,score:milvus相似度的分,type:milvus},{chunk_id,content,...,score:milvus相似度的分,type:milvus}
    for weight, chunks  in data_list: # 遍历路
        for rank,chunk in enumerate(chunks,start=1): # 每路的数据chunk
            rrf_score = weight * (1/(k+rank))
            chunk_id = chunk.get("chunk_id")
            # 每次存之前都先取! 没有存过就是0 [1.第一路 2.第二路对应第一路没存]
            score_dict[chunk_id] = score_dict.get(chunk_id,0.0) + rrf_score
            #chunk_dict[chunk_id] = chunk  # 消除重复! 同一个chunk_id只保留一份 [最后一个]
            chunk_dict.setdefault(chunk_id,chunk)  # 消除重复! 同一个chunk_id只保留一份 [第一个]
    # 循环后处理结果
    # {chunk_id:chunk{score -> milvus单路的分 => rrf融合分 }} {chunk_id:score}
    rrf_chunks:list[dict] = []
    for chunk_id,chunk in chunk_dict.items():
        # score -> milvus单路的分 => rrf融合分
        chunk['score'] = score_dict.get(chunk_id)
        rrf_chunks.append(chunk)

    # rrf_chunks进行排名
    logger.debug(f"排序之前内容: {rrf_chunks}")
    rrf_chunks.sort(key=lambda c : c.get("score",0.0),reverse=True)
    logger.debug(f"排序之后内容: {rrf_chunks}")

    # 截取分最高的top
    # 假设 top5
                    # node_rrf top 5
    # 问题 top5
    # todo: 固定截取的topk = 5 动态解决!
    rrf_chunks = rrf_chunks[:HYBRID_SEARCH_LIMIT_NUMBER]
    return rrf_chunks

@step_log("fuse_by_rrf")
def fuse_by_rrf(state: QueryGraphState) -> QueryGraphState:
    # 1. 获取并校验参数(state) embedding_chunks  hyde_embedding_chunks
    embedding_chunks,hyde_embedding_chunks = validate_and_get_data(state)
    # 2. 使用rrf的排名逻辑
    # 提前配置好了每一路的权重... [权重值后续改为config.py常量]
    data_list:list[tuple[float,list]] = [
        (0.5,embedding_chunks),
        (0.5,hyde_embedding_chunks)
    ]
    rrf_chunks = reciprocal_rank_fusion(data_list)
    # 3. 更新state
    state['rrf_chunks'] = rrf_chunks
    return state