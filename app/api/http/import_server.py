import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse

from app.api.schema.import_schema import StatusResponseSchema, UploadResponseSchema
from app.process.import_.agent.main_graph import import_graph_app
from app.process.import_.agent.state import create_default_state, ImportGraphState
from app.shared.runtime.logger import logger,PROJECT_ROOT
from mimetypes import guess_type
from app.shared.utils.task_utils import get_running_task_list,get_done_task_list,get_task_status , update_task_status , TASK_STATUS_PROCESSING , TASK_STATUS_COMPLETED,TASK_STATUS_FAILED
from datetime import datetime


app = FastAPI()

# 接口1: 返回html文件
@app.get("/html")
def return_html():
    # 拼接html地址
    html_path_obj:Path = PROJECT_ROOT / "app" / "resources" / "htmls" / "import.html"
    # 返回响应File
    return FileResponse(
        # filename=,
        path= str(html_path_obj),
        media_type=guess_type(html_path_obj.name)[0]
    )

# 接口2: 返回指定task_id的任务状态
@app.get("/status/{task_id}")
def return_status(task_id:str):

    # 任务状态 / 运行 / 完成 -> task_util
    # 运行的列表
    running_list = get_running_task_list(task_id)
    # 完成列表
    done_list    = get_done_task_list(task_id)
    # 任务状态
    status = get_task_status(task_id) # 在哪存的状态的: 执行的接口调用图的存既可以!  status 值要怎么写: processing failed completed

    return StatusResponseSchema(
        code = 200,
        task_id=task_id,
        status=status,
        done_list=done_list,
        running_list=running_list
    )


def invoke_import_graph(task_id:str,local_file_path:str,local_dir:str):

    # 1.创建state
    state: ImportGraphState = create_default_state(
        # local_file_path:str
        local_file_path=local_file_path,
        local_dir=local_dir,
        # task_id:str
        task_id=task_id
    )
    logger.info(f"开始流程测试,测试数据:{json.dumps(state, indent=4, ensure_ascii=False)}")

    try:
        update_task_status(task_id,TASK_STATUS_PROCESSING)
        # 图
        result: ImportGraphState = import_graph_app.invoke(state)
        update_task_status(task_id,TASK_STATUS_COMPLETED)
    except Exception as e:
        update_task_status(task_id,TASK_STATUS_FAILED)
        logger.exception(e)


# 接口3: 文件上传接口实现
@app.post("/upload")
async def upload_files(task:BackgroundTasks,files:list[UploadFile]):

    #1. 本次文件生成一个唯一的id
    # uuid -> 技术 -> 随机不重复字符串 -> 时区 / 时间戳 / ip地址 / mac地址 ..
    task_id = str(uuid.uuid4())
    #2. 转存文件  /output/时间/task_id/filename
    upload_file:UploadFile = files[0]
    # state local_file_path
    local_dir_obj:Path = PROJECT_ROOT / "output" / datetime.now().strftime("%Y%m%d") / task_id
    local_dir_obj.mkdir(parents=True,exist_ok=True)
    local_file_path_obj:Path = local_dir_obj / upload_file.filename
    # 上传数据
    data = await upload_file.read()
    local_file_path_obj.write_bytes(data = data)
    #3. 异步调用图的执行过程
    task.add_task(invoke_import_graph,task_id=task_id,local_file_path=str(local_file_path_obj),local_dir=str(local_dir_obj))
    #4. 返回结果
    return UploadResponseSchema(
        code=200,
        message=f"{upload_file.filename}已经开始进行解析了!",
        task_ids=[task_id]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app=app,host="0.0.0.0",port=8000) #端口号是固定! 前端页面是写死的 8000