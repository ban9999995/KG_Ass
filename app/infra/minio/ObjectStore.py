# 封装minio的公共模块类! 方便统一调用!
from app.infra.config.providers import infra_config
from app.shared.clients.minio_utils import get_minio_client
from app.shared.runtime.logger import logger

class MinioGateway:

    # 1.返回桶名
    @property
    def bucket_name(self):
        return infra_config.minio_config.bucket_name
    # 2.图片的公共前缀
    @property
    def images_prefix(self):
        return infra_config.minio_config.minio_img_dir
    # 3.返回客户端
    @property
    def minio(self):
        return get_minio_client()
    # 4.拼接访问地址
    def build_image_url(self,object_name:str) -> str:
        """
        拼接访问地址 注意: object_name 必须使用 / 开头
        :param object_name: /upload-images/文件名/图片名.jpg
        :return:
        """
        # 没有http / https :// + 端点 + 桶名 + 对象名
        prefix = "https://" if infra_config.minio_config.minio_secure else "http://"
        image_url = f"{prefix}{infra_config.minio_config.endpoint}/{infra_config.minio_config.bucket_name}{object_name}"
        logger.info(f"为:{object_name}拼接minio的访问地址为:{image_url}")
        return image_url

minio_gateway = MinioGateway()
