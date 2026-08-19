from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import RERANK_MAX_INPUT_TOKENS, RERANK_SUMMARY_CHAR_RATIO, RERANK_MIN_SUMMARY_CHARS, \
    RERANK_MAX_TOPK, RERANK_MIN_TOPK, RERANK_GAP_RATIO, RERANK_GAP_ABS
from app.shared.runtime.logger import logger, step_log
from app.infra.model.model_providers import model_provider
from app.shared.runtime.load_prompt import load_prompt

# 1. 获取并校验参数  node_rrf web_search
@step_log("get_data_and_validate")
def get_data_and_validate(state:QueryGraphState) -> tuple[str,list,list]:
    # 获取数据
    rewritten_query = state.get("rewritten_query")
    rrf_chunks      = state.get("rrf_chunks")
    web_search_docs = state.get("web_search_docs")
    # 非空判断
    if not rewritten_query or not rrf_chunks or not web_search_docs:
        logger.error(f"rewritten_query或者rrf_chunks或者web_search_docs为空,业务无法继续,提前终止!!")
        raise ValueError(f"rewritten_query或者rrf_chunks或者web_search_docs为空,业务无法继续,提前终止!!")
    # 返回即可
    return rewritten_query,rrf_chunks,web_search_docs

# 2. 将两路数据融合到一个列表 node_rrf web_search -> list[{},{},{}]
@step_log("merge_rrf_and_web")
def merge_rrf_and_web(rrf_chunks:list[dict],web_search_docs:list[dict]) -> list[dict]:
    # rrf_chunks -> [{chunk_id,file_title,title,parent_title,part,item_name,content,type,score}]
    # web_search_docs -> [{title,content,url,type}]
    logger.info(f"合并数据之前的长度:{len(rrf_chunks)}")
    rrf_chunks.extend(web_search_docs)
    logger.info(f"合并数据之后的长度:{len(rrf_chunks)}")
    return rrf_chunks

# 3. 拼接问题+答案对的列表,问题+答案超过了上下文窗口,启动压缩 -> list[[],[]]
@step_log("create_question_answer_pair")
def create_question_answer_pair(merge_list:list[dict],rewritten_query:str) -> list[tuple[str,str]]:
    # todo: 粘贴常量
    """
    RERANK_MAX_TOPK: int = 10
    RERANK_MIN_TOPK: int = 1
    RERANK_GAP_RATIO: float = 2
    RERANK_GAP_ABS: float = 2
    RERANK_MAX_INPUT_TOKENS: int = 512
    RERANK_SUMMARY_CHAR_RATIO: float = 1.3
    RERANK_MIN_SUMMARY_CHARS: int = 50
    """
    # [[问题,答案]]
    # 1.定义个问题和答案对的列表
    question_answer_pair:list[tuple[str,str]] = []
    # 2.问题对应的token数量计算出来
    question_token_number:int = model_provider.compute_token_number(rewritten_query)
    # 3.循环遍历 merge_list -> content answer
    for chunk in merge_list:
        # 4.计算answer的长度token
        answer:str = chunk.get("content")
        answer_token_number:int = model_provider.compute_token_number(answer)
        # 判断长度
        if (question_token_number + answer_token_number) > RERANK_MAX_INPUT_TOKENS:
            # 5.answer长度 + 问题token长度大于最大窗口的有效数量 -> 启动压缩 -> 添加到问题对
            # 5.1 加载模型
            llm_model = model_provider.llm_model()
            # 5.2 加载提示词
            # (RERANK_MAX_INPUT_TOKENS - question_token_number) / RERANK_SUMMARY_CHAR_RATIO -> 10字符
            # 接收截取,总结清晰! 最低 50
            limit:int = max(RERANK_MIN_SUMMARY_CHARS,
                            int((RERANK_MAX_INPUT_TOKENS - question_token_number) / RERANK_SUMMARY_CHAR_RATIO))
            refine_prompt:str = load_prompt("rerank_text_refine",question=rewritten_query,answer=answer,limit=limit)
            messages = [
                HumanMessage(
                    content=refine_prompt
                )
            ]
            # 链
            chains = llm_model | StrOutputParser()
            # 执行
            logger.debug(f"压缩之前的answer:{answer}")
            answer:str = chains.invoke(messages)
            logger.debug(f"压缩之后目标长度:{limit},最终answer:{answer}")
        # 6.answer长度 + 问题token长度小于最大窗口的有效数量 -> 添加到问题对
        question_answer_pair.append((
            rewritten_query,answer
        ))
    # 7.返回问题对即可
    return question_answer_pair


#4. 进行内容答问 (问题+答案对的列表) -> list [0.8,0.9,0.2,0.75]
@step_log("call_reranker_compute_scores")
def call_reranker_compute_scores(question_answer_pair:list[tuple[str,str]]) -> list[float]:
    """
      嵌入式模型: 稠密向量进行归一化处理  ip / cosine
      混合检索 : WeightReranker( , 归一化= True) ->  0 - 1
      reranker: compute_scores(question_answer_pair,normalize=True) -> 分 -> 0 - 1 分
    """
    scores_list:list[float] = model_provider.compute_scores(question_answer_pair)
    # scores_list == question_answer_pair = merge_list
    logger.info(f"已经完成:{question_answer_pair}的数据打分,\n分值为:{scores_list}")
    return scores_list

#5. 将分值回填到  list[{},{},{score}],根据score倒序排序 -> list[{},{},{}]
@step_log("set_merged_score_and_sort")
def set_merged_score_and_sort(scores:list[float],merge_list:list[dict]) -> list[dict]:
    # 遍历处理
    for score,chunk in zip(scores,merge_list):
        chunk['score'] = score
    logger.info(f"完成分数回调:{merge_list}")
    # 排序即可
    merge_list.sort(key=lambda i:i.get("score",0.0),reverse=True)
    logger.info(f"完成排序后的数据:{merge_list}")

#6. 动态断崖检查,动态截取 list[{},{},{}] -> list[{},{},{}]
@step_log("dynamic_top_k")
def dynamic_top_k(merge_list:list[dict]) -> list[dict]:
    """
      RERANK_MAX_TOPK: int = 10  # 动态截取数量,最多10个!
      RERANK_MIN_TOPK: int = 3   # 动态截取数量,最少3个!
      RERANK_GAP_RATIO: float = 0.2  20% # 断崖的百分比       前 - 后 / 前 = 百分比  [分值都比较小的时候!]  0.33   0.3  0.2
      RERANK_GAP_ABS: float = 0.2        # 断崖的分数绝对值   前 - 后 = 断崖分  0.1  []
    """
    max_top_k = RERANK_MAX_TOPK
    min_top_k = RERANK_MIN_TOPK
    ratio     = RERANK_GAP_RATIO
    rerank_abs= RERANK_GAP_ABS
    # todo: 连续'断崖',自行扩展!  [0.9 0.8 0.7 0.6 0.5 0.4]-> 0.1
    # 1. max大于长度处理
    max_top_k = min(max_top_k,len(merge_list))
    # 2. 整个过程没有断崖
    number    = max_top_k
    # 3. max > min的场景才需要循环
    if max_top_k > min_top_k:
        # 4.循环找断崖
        for index in range(min_top_k-1,max_top_k-1):
            pre_score  = merge_list[index].get("score",0.0)
            next_score = merge_list[index+1].get("score",0.0)
            abs_score  = pre_score - next_score
            ratio_score= abs_score / (pre_score + 1e-7) # 避免除零报错
            # 断崖判断
            if abs_score > rerank_abs or ratio_score > ratio:
                number = index + 1 #number是截取的数量
                logger.info(f"检查发现存在断崖,前分:{pre_score},后分:{next_score},截取数量:{number}")
                break
    # 4. 动态截取
    reranked_docs = merge_list[:number]
    return reranked_docs

@step_log("rerank_documents")
def rerank_documents(state: QueryGraphState) -> QueryGraphState:
    # 1.获取并校验参数
    rewritten_query,rrf_chunks,web_search_docs = get_data_and_validate(state)
    # 2. 做两路数据融合
    merge_list:list[dict] = merge_rrf_and_web(rrf_chunks,web_search_docs)
    # 3. 创建问题和答案的对(完成压缩)
    question_answer_pair:list[list[str]] = create_question_answer_pair(merge_list,rewritten_query)
    # 4. 调用rerank模型进行打分
    score_list:list[float] = call_reranker_compute_scores(question_answer_pair)
    # 5. 分数回填和排序
    set_merged_score_and_sort(score_list,merge_list)
    # merge_list -> [{chunk_id,....,score:0.9},{chunk_id,....,score:0.9}]
    # 6. 动态断崖处理
    reranked_docs = dynamic_top_k(merge_list)
    # 7. 更新state reranked_docs,并且返回即可
    state['reranked_docs'] = reranked_docs
    return state