import asyncio
import time
from pathlib import Path

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import PARSE_PDF_OUTPUT_DIR, MINERU_MODEL_VERSION, MINERU_DOWNLOAD_TIMEOUT_SECONDS, \
    MINERU_POLL_INTERVAL_SECONDS, MINERU_POLL_TIMEOUT_SECONDS
from app.shared.runtime.logger import logger ,PROJECT_ROOT
from app.infra.config.providers import infra_config
import requests


#  validate_data_and_paths(state) -> tuple[Path]
#          步骤1: 获取参数 pdf_path , local_dir -> str
#          步骤2: 非空校验
#                pdf_path  -> 空 -> 不行 -> error
#                local_dir -> 空 -> 行   -> warning
#          步骤3: 将字符串转成Path
#          步骤4: 存在性校验
#                pdf_path -> 对应的文件 -> 没有 -> error FileNotFoundError
#                local_dir -> 对应的文件夹-> 没有 -> warning 创建即可
#          步骤5: 返回结果  Path

def validate_data_and_paths(state:ImportGraphState) -> tuple[Path]:
    # 步骤1: 获取参数 pdf_path , local_dir -> str
    pdf_path:str  = state.get("pdf_path")
    local_dir:str = state.get("local_dir")
    # 步骤2: 非空校验
    if not pdf_path:
        logger.error(f"pdf_path为空,没有文件可以解析,业务无法继续,提前终止!")
        raise ValueError(f"pdf_path为空,没有文件可以解析,业务无法继续,提前终止!")
    if not local_dir:
        # local_dir -> str -> Path
        local_dir:Path = PROJECT_ROOT / PARSE_PDF_OUTPUT_DIR
        logger.warning(f"local_dir为空,为了业务继续进行,给与默认值:{str(local_dir)}")
    # 步骤3: 将字符串转成Path
    pdf_path_obj:Path = Path(pdf_path)
    # Path( | str | __file__ | Path)
    local_dir_obj:Path = Path(local_dir)
    # 步骤4: 存在性校验
    if not pdf_path_obj.is_file():
        logger.error(f"{str(pdf_path_obj)}有地址,但是没有具体的文件,业务无法继续,提前终止!!")
        raise FileNotFoundError(f"{str(pdf_path_obj)}有地址,但是没有具体的文件,业务无法继续,提前终止!!")
    if not local_dir_obj.is_dir():
        logger.warning(f"{str(local_dir_obj)}地址没有对应的文件夹,我们提前创建!!")
        local_dir_obj.mkdir(parents=True,exist_ok=True)
    # 步骤5: 返回结果
    return pdf_path_obj,local_dir_obj


#upload_pdf_and_poll(pdf_path_obj:Path) -> str:
def upload_pdf_and_poll(pdf_path_obj:Path) -> str:
    # 1. 向minerU申请文件上传地址(获取上传地址/batch_id)
    token = infra_config.mineru_config.api_key
    url = f"{infra_config.mineru_config.base_url}/file-urls/batch"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "files": [
            {"name": f"{pdf_path_obj.name}"}
        ],
        "model_version": MINERU_MODEL_VERSION
    }
    """
      requests  . get / post / put / delete (url,headers=请求头的字典,params={ param } , json=字典 data=字节数据 , timeout=xx)
    """
    response = requests.post(url=url,headers = header ,json=data , timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
    # 获取上传地址/batch_id
    # 判断状态成功: 1. 标准的接口 先判断响应状态码 status_code 再判断接口的业务状态 code 2. 非标准接口http地址 直接判断状态码
    status_code =  response.status_code
    if status_code != 200:
        logger.error(f"向minerU申请文件解析地址,网络状态错误:{status_code},业务无法继续,提前终止!!")
        raise RuntimeError(f"向minerU申请文件解析地址,网络状态错误:{status_code},业务无法继续,提前终止!!")
    # 响应体的json字符串  .content .text .json() -> json - dict
    response_json_dict:dict = response.json()
    code = response_json_dict.get("code",-1)
    if code != 0:
        logger.error(f"向minerU申请文件解析地址,业务状态错误:{code},业务无法继续,提前终止!!")
        raise RuntimeError(f"向minerU申请文件解析地址,业务状态错误:{code},业务无法继续,提前终止!!")
    # 获取上传地址 / batch_id
    batch_id:str = response_json_dict.get("data",{}).get("batch_id")
    file_urls:list[str] = response_json_dict.get("data",{}).get("file_urls",[])
    # 非空校验
    if not batch_id:
        logger.error(f"向minerU申请文件解析地址,结果中batch_id为空,业务无法继续,提前终止!!")
        raise RuntimeError(f"向minerU申请文件解析地址,结果中batch_id为空,业务无法继续,提前终止!!")
    if not file_urls:
        logger.error(f"向minerU申请文件解析地址,结果中file_urls为空,业务无法继续,提前终止!!")
        raise RuntimeError(f"向minerU申请文件解析地址,结果中file_urls为空,业务无法继续,提前终止!!")
    file_url:str = file_urls[0]
    logger.info(f"成功向minerU申请到文件解析地址,batch_id:{batch_id},file_url:{file_url}")
    # 2. 向指定地址发起请求上传pdf文件
    # put 传递文件 -> 不是标准接口 http文件服务器
    """
      pdf_path_obj  str : Path
      with open(pdf_path_obj,mode="rb") as f:
      Path  name stem suffix parent parents
            read_bytes() write_bytes()
            read_text()    write_text()
    """
    # with open(file,mode="rb r w wb",encoding="utf-8") as f:
    #     f.read()
    with requests.Session() as session:
        # file_url -> minerU的文件服务器地址,正常文件服务器上传需要认证!  minerU的文件服务器地址 地址直接添加了预签名信息
        # [预签名地址,服务器校验越严格! 如果我们在请求中携带无关的头! 直接抛异常!!]
        data = pdf_path_obj.read_bytes()
        """
          requests.put(url) -> 携带当前电脑环境中的网络配置(代理) -> 请求头中无关的代理参数 -> 文件服务器中
          session -> .trust_env = False -> 直接使用put函数指定的参数 -> 文件服务器发起请求 -> 不会携带电脑环境中的代理参数 -> 成功
        """
        session.trust_env = False
        upload_response = session.put(url=file_url,data=data)
        upload_status_code = upload_response.status_code
        if upload_status_code != 200:
            logger.error(f"向指定地址:{file_url}上传文件失败!状态码为:{upload_status_code},业务无法继续,提前终止!")
            raise RuntimeError(f"向指定地址:{file_url}上传文件失败!状态码为:{upload_status_code},业务无法继续,提前终止!")
    logger.info(f"将文件传递到minerU指定的文件服务器中,状态成功!!")
    # 3. 使用batch_id轮询获取解析结果,提取zip_url
    # 准备工作 1. 请求地址 2.间隔时间 3.最大等待时间
    url = f"{infra_config.mineru_config.base_url}/extract-results/batch/{batch_id}"
    interval_time = MINERU_POLL_INTERVAL_SECONDS  # 3秒   -> 自己试
    timeout_time  = MINERU_POLL_TIMEOUT_SECONDS   # 600秒 -> 每页pdf -> 预估1秒
    current_time  = time.time()
    # 轮询就是一个死循环! 满足条件跳出 不满足不超时  continue
    while True:
        # 3.1 有没有超出等待时间
        if time.time() - current_time > timeout_time:
            logger.error(f"轮询获取解析结果超时,提前终止业务!")
            raise TimeoutError(f"轮询获取解析结果超时,提前终止业务!")
        # 3.2 没有申请状态请求
        poll_response = requests.get(url,headers=header)
        # 3.3 判断网络状态码
        if poll_response.status_code != 200:
            # 不等于200,但是可以给与机会! 5xx是给机会! 服务器的问题可能修改!!
            if 500 <= poll_response.status_code < 600:
                # 可以给机会
                logger.warning(f"轮询获取解析结果,状态码为:{poll_response.status_code},给与机会,再次尝试!")
                time.sleep(interval_time) # 线程
                #asyncio.sleep() 协程
                continue
            else:
                logger.error(f"轮询获取解析结果,状态码为:{poll_response.status_code},业务无法继续,提前终止!!")
                raise RuntimeError(f"轮询获取解析结果,状态码为:{poll_response.status_code},业务无法继续,提前终止!!")
        # 3.4 判断业务状态码
        poll_response_dict:dict =  poll_response.json()
        poll_code = poll_response_dict.get("code",-1)
        # 不等于0抛出异常
        if poll_code != 0:
            logger.error(f"向minerU获取文件解析结果,业务状态错误:{poll_code},业务无法继续,提前终止!!")
            raise RuntimeError(f"向minerU获取文件解析结果,业务状态错误:{poll_code},业务无法继续,提前终止!!")
        # 3.5 解析获取结果
        poll_result_dict:dict = poll_response_dict.get("data",{}).get("extract_result",[])[0]
        poll_state            = poll_result_dict.get("state")

        if poll_state == "done":
            full_zip_url = poll_result_dict.get("full_zip_url")
            logger.info(f"向minerU获取文件解析结果,解析状态:成功,下载地址:{full_zip_url},结束方法!")
            return full_zip_url
        elif poll_state == "failed":
            logger.error(f"向minerU获取文件解析结果,解析状态:失败,业务无法继续,提前终止!!")
            raise RuntimeError(f"向minerU获取文件解析结果,解析状态:失败,业务无法继续,提前终止!!")
        else:
            # 没失败,没解析完!
            logger.info(f"向minerU获取文件解析结果,解析状态:{poll_state},正在解析中,稍后再试!")
            time.sleep(interval_time)
            continue


def parse_pdf_to_markdown(state: ImportGraphState) -> ImportGraphState:
    # 1. 获取请求参数并且校验 -> 函数  pdf_path , local_dir
    pdf_path_obj,local_dir_obj = validate_data_and_paths(state)
    # 2. minerU申请解析和文件上传以及轮询获取解析结果
    full_zip_url:str = upload_pdf_and_poll(pdf_path_obj)

    return state