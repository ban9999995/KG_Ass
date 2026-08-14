from typing import Any

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import CHUNKS_SPLIT_BATCH_SIZE
from app.shared.runtime.logger import logger, step_log
from app.infra.model.model_providers import model_provider

# 1. 获取参数并且校验
@step_log("get_data_and_validate")
def get_data_and_validate(state:ImportGraphState)-> list[dict[str,Any]]:
    # chunks
    chunks = state.get("chunks")
    # 非空校验
    if not chunks:
        logger.error(f"chunks为空,业务无法继续,提前终止!!")
        raise ValueError(f"chunks为空,业务无法继续,提前终止!!")
    # 返回数据
    return chunks

# 2. 批量生成向量
@step_log("batch_create_chunks_vector")
def batch_create_chunks_vector(chunks:list[dict[str,Any]]):
    """
      每个五个一批 批量生成
    :param chunks:
    :return:
    """
    chunks_size = len(chunks)

    # 批量循环
    for index  in range(0,chunks_size,CHUNKS_SPLIT_BATCH_SIZE):
        # chunks_size -> 13
        # index - 0 - 4  index - 5 - 9  index - 10 - 12
        current_chunks:list[dict[str,Any]] = chunks[index:index+CHUNKS_SPLIT_BATCH_SIZE]
        #  item_name : content -> 向量
        current_content_list:list[str] = [f"{chunk.get('item_name')}:{chunk.get('content')}" for chunk in current_chunks]
        # 批量生成向量即可
        # result = {"dense":[[]],"sparse":[{}]}
        result = model_provider.create_embeddings(current_content_list)
        # 进行数据回显 向量 -> current_chunks
        for sub_index, chunk in enumerate(current_chunks):
            chunk['dense_vector'] = result['dense'][sub_index]
            chunk['sparse_vector'] = result['sparse'][sub_index]
        logger.debug(f"第{index+1}批数据处理完毕!本次处理长度:{len(current_chunks)}")

# 3. 更新state并返回..
@step_log("generate_chunk_embeddings")
def generate_chunk_embeddings(state: ImportGraphState) -> ImportGraphState:
    """
    向量化服务：
    1. 读取 chunks
    2. 生成 dense_vector / sparse_vector
    3. 将向量结果补充回 chunks
    """
    # 1.获取并校验参数
    chunks = get_data_and_validate(state)
    # 2.批量生成向量
    batch_create_chunks_vector(chunks)
    # 3. 更新state并返回
    state['embeddings_content'] = chunks
    return state