"""
工具模块，负责提供 reranker 相关的辅助能力。
"""
from pathlib import Path

from FlagEmbedding import FlagReranker

from app.shared.config.reranker_config import reranker_config
from app.shared.runtime.logger import logger, PROJECT_ROOT

_reranker_model: FlagReranker | None = None


def get_reranker_model() -> FlagReranker:
    """
    获取重排模型单例对象。

    Returns:
        FlagReranker: 初始化完成的重排模型实例。
    """
    global _reranker_model
    if _reranker_model is None:
        logger.info("开始初始化重排模型")
        model_name_or_path = reranker_config.bge_reranker_large
        # 相对路径统一基于项目根目录解析为绝对路径，避免因 CWD 不同导致找不到本地模型
        candidate = PROJECT_ROOT / model_name_or_path
        if not Path(model_name_or_path).is_absolute() and candidate.exists():
            model_name_or_path = str(candidate)
        _reranker_model = FlagReranker(
            model_name_or_path=model_name_or_path,
            device=reranker_config.bge_reranker_device,
            use_fp16=reranker_config.bge_reranker_fp16,
        )
        logger.success("重排模型初始化成功")
    return _reranker_model
