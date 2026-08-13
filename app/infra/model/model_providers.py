from app.shared.model.embedding_utils import generate_embeddings
from app.shared.model.lm_utils import get_llm_client

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

model_provider = ModelProvider()