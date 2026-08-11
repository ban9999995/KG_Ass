import re
from pathlib import Path
from typing import Any

from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger


#1. 获取参数和校验
def validate_data_and_content(state:ImportGraphState) -> tuple[str,str,Path]:
    # 1.1 获取参数 md_content / md_path  / file_title
    md_content:str = state.get("md_content")
    md_path   :str = state.get("md_path")
    file_title:str = state.get("file_title")
    # 1.2 非空校验 md_path为空不可以的!  file_title md_path读取 md_content  为空从md_path读取
    if not md_path:
        logger.error(f"md_path为空,业务无法继续,提前终止!")
        raise ValueError(f"md_path为空,业务无法继续,提前终止!")
    md_path_obj:Path = Path(md_path)
    if not md_path_obj.is_file():
        logger.error(f"md_path有值:{md_path},但是没有真实的文件! 业务无法继续,提前终止!")
        raise FileNotFoundError(f"md_path有值:{md_path},但是没有真实的文件! 业务无法继续,提前终止!")
    if not md_content:
        logger.warning(f"在state中没有获取到md_content值,我们利用md_path再次读取!")
        md_content:str = md_path_obj.read_text(encoding="utf-8")
        state['md_content'] = md_content
    if not file_title:
        logger.warning(f"在state中没有获取file_title,我们利用md_path再次读取!")
        file_title  = md_path_obj.stem
        state['file_title'] = file_title
    # 1.3 统一换行符号  md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    # 1.4 返回三个参数即可
    return md_content,file_title,md_path_obj



def split_document(state: ImportGraphState) -> ImportGraphState:
    """
    文档切分服务：
    1. 按标题层级做一级粗切
    2. 对超长文本做二次细切
    3. 构造 chunks 列表
    4. 回写 chunks
    """
    return state