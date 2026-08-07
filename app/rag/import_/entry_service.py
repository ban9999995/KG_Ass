from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger, step_log
from pathlib import Path


@step_log("resolve_input_file")
def resolve_input_file(state: ImportGraphState) -> ImportGraphState:
    # 1. state中获取参数 local_file_path
    # local_file_path:str = state['local_file_path']  # -> 没有报错的!!
    local_file_path:str = state.get("local_file_path") # -> 没有属性key也不报错
    # 2. [每个节点参数校验工作->健壮性->鲁棒性] local_file_path非空判断即可
    if not local_file_path:
        # 为空了,业务无法继续进行,提前异常终止!
        # BaseException -> Exception -> Error
        logger.error(f"local_file_path没有赋值,没有文件可以解析,业务无法继续进行,提前终止!")
        raise ValueError(f"local_file_path没有赋值,没有文件可以解析,业务无法继续进行,提前终止!")
    # 3. 判断文件类型,后缀名(.md / .pdf)  xx.md  xx.MD
    if local_file_path.lower().endswith(".md"):
        # md
        state['md_path'] = local_file_path
        state['is_md_read_enabled'] = True
        state['pdf_path'] = None
        state['is_pdf_read_enabled'] = False
    elif local_file_path.lower().endswith(".pdf"):
        # pdf
        state['md_path'] = None
        state['is_md_read_enabled'] = False
        state['pdf_path'] = local_file_path
        state['is_pdf_read_enabled'] = True
    else:
        state['md_path'] = None
        state['is_md_read_enabled'] = False
        state['pdf_path'] = None
        state['is_pdf_read_enabled'] = False
    # 扩展文件类型 elif...
    # 4. 是md -> 修改 md_path is_md_read_enabled -> 正值  pdf_path is_pdf_enabled -> 反值
    # 5. 是pdf -> 修改 md_path is_md_read_enabled -> 反值  pdf_path is_pdf_enabled -> 正值
    # 6. 都不是 -> md_path is_md_read_enabled -> 反值  pdf_path is_pdf_enabled -> 反值
    #7. local_file_path对应的文件名获取到file_title
    #  c://xxx/xxx/info.md -> file_title -> info
    #  思路: 字符串处理思路 -> 路径思路 os.path  path.join(1,2,3) <- [ pathlib Path]
    #  包裹成Path对象 1. Path() [相对] 2.Path(__file__) [对象] -> 当前文件的Path对象  3.Path(地址) 对象的属性或者函数
    local_file_path_obj:Path = Path(local_file_path)
    # stem -> 没有后缀的名字  name -> 全名称带后缀  suffix 后缀
    file_title = local_file_path_obj.stem
    # 8. 更新state并返回即可
    state['file_title'] = file_title
    return state