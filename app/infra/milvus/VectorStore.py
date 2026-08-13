from app.infra.config.providers import infra_config
from app.shared.clients.milvus_utils import get_milvus_client

class MilvusGateway:

    # 3个返回属性的函数
    @property
    def chunk_collection_name(self):
        return infra_config.milvus_config.chunks_collection

    @property
    def item_name_collection_name(self):
        return infra_config.milvus_config.item_name_collection

    # @property
    # def dense_dim(self):
    #     return infra_config.milvus_config.

    # 1个返回客户端的函数
    @property
    def milvus_client(self):
        return get_milvus_client()

milvus_gateway = MilvusGateway()