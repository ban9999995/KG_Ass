from transformers import AutoTokenizer

from app.shared.model.embedding_utils import generate_embeddings
from app.shared.model.lm_utils import get_llm_client
from app.shared.model.reranker_utils import get_reranker_model

class ModelProvider:
    # 1. 获取大语言模型
    def llm_model(self,model_name:str|None=None,json_mode:bool=False):
        return get_llm_client(model=model_name,json_mode=json_mode)
    # 2. 获取视觉模型
    def vision_model(self,model_name:str):
        return get_llm_client(model=model_name)
    # 3. 嵌入式模型生成向量的函数
    def create_embeddings(self,texts: list[str])-> dict[str, list]:
        return generate_embeddings(texts)
    # 4. reranker模型  打分 = 算token数量
    def compute_scores(self,question_answer_pair:list[list[str]]) -> list[float]:
        reranker_model = get_reranker_model()
        score_list: list[float] = reranker_model.compute_score(question_answer_pair,normalize=True)
        return score_list
    def compute_token_number(self,data:str)->int:
        reranker_model = get_reranker_model()
        tokenizer = reranker_model.tokenizer
        # encode() 获取字符串转成token的id的列表!
        # add_special_tokens -> 计算token的时候,不要考虑特殊字符(分割字符)  514 - 2 -4 = 508
        token_id_list =  tokenizer.encode(data,add_special_tokens=False)
        token_number:int = len(token_id_list)
        return token_number


model_provider = ModelProvider()