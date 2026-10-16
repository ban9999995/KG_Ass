import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.schema.import_schema import StatusResponseSchema, UploadResponseSchema, KnowledgePermissionRequest
from app.process.import_.agent.main_graph import import_graph_app
from app.process.import_.agent.state import create_default_state, ImportGraphState
from app.shared.runtime.logger import logger,PROJECT_ROOT
from mimetypes import guess_type
from app.shared.utils.task_utils import get_running_task_list,get_done_task_list,get_task_status , update_task_status , TASK_STATUS_PROCESSING , TASK_STATUS_COMPLETED,TASK_STATUS_FAILED
from datetime import datetime
from app.rag.knowledge.knowledge_unit_service import knowledge_unit_store


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


def invoke_import_graph(task_id:str,local_file_path:str,local_dir:str,knowledge_unit_id:str = ""):

    # 1.创建state
    state: ImportGraphState = create_default_state(
        # local_file_path:str
        local_file_path=local_file_path,
        local_dir=local_dir,
        # task_id:str
        task_id=task_id,
        knowledge_unit_id=knowledge_unit_id,
    )
    logger.info(f"开始流程测试,测试数据:{json.dumps(state, indent=4, ensure_ascii=False)}")

    try:
        update_task_status(task_id,TASK_STATUS_PROCESSING)
        # 图
        result: ImportGraphState = import_graph_app.invoke(state)
        if knowledge_unit_id:
            knowledge_unit_store.transition(knowledge_unit_id, "DRAFT")
        update_task_status(task_id,TASK_STATUS_COMPLETED)
    except Exception as e:
        if knowledge_unit_id:
            try:
                knowledge_unit_store.transition(knowledge_unit_id, "FAILED")
            except Exception:
                logger.exception("更新知识单元失败状态失败")
        update_task_status(task_id,TASK_STATUS_FAILED)
        logger.exception(e)


# 接口3: 文件上传接口实现
@app.post("/upload")
async def upload_files(task:BackgroundTasks,files:list[UploadFile]):
    if not files:
        raise HTTPException(status_code=422, detail="至少上传一个文档")
    allowed_suffixes = {".pdf", ".md", ".docx", ".txt"}
    task_ids: list[str] = []
    knowledge_unit_ids: list[str] = []
    for upload_file in files:
        filename = Path(upload_file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in allowed_suffixes:
            raise HTTPException(status_code=415, detail=f"不支持的文档格式: {filename or 'unknown'}")
        task_id = str(uuid.uuid4())
        local_dir_obj:Path = PROJECT_ROOT / "output" / datetime.now().strftime("%Y%m%d") / task_id
        local_dir_obj.mkdir(parents=True,exist_ok=True)
        local_file_path_obj:Path = local_dir_obj / filename
        with local_file_path_obj.open("wb") as file_buffer:
            shutil.copyfileobj(upload_file.file, file_buffer)
        unit = knowledge_unit_store.create(
            title=local_file_path_obj.stem,
            file_format=suffix.lstrip("."),
            source_filename=filename,
        )
        knowledge_unit_store.transition(unit["knowledge_unit_id"], "PROCESSING")
        task.add_task(
            invoke_import_graph,
            task_id=task_id,
            local_file_path=str(local_file_path_obj),
            local_dir=str(local_dir_obj),
            knowledge_unit_id=unit["knowledge_unit_id"],
        )
        task_ids.append(task_id)
        knowledge_unit_ids.append(unit["knowledge_unit_id"])
    return UploadResponseSchema(
        code=200,
        message=f"已接收 {len(task_ids)} 个文档，开始解析!",
        task_ids=task_ids,
        knowledge_unit_ids=knowledge_unit_ids,
    )


@app.get("/knowledge-units")
def list_knowledge_units(
        keyword: str = Query(default=""),
        status: str = Query(default=""),
        format: str = Query(default=""),
):
    return {"code": 200, "data": knowledge_unit_store.list(keyword=keyword, status=status, file_format=format)}


@app.get("/knowledge-units/{knowledge_unit_id}")
def get_knowledge_unit(knowledge_unit_id: str):
    item = knowledge_unit_store.get(knowledge_unit_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识单元不存在")
    return {"code": 200, "data": item}


def _transition_knowledge_unit(knowledge_unit_id: str, target: str):
    try:
        item = knowledge_unit_store.transition(knowledge_unit_id, target)
    except KeyError:
        raise HTTPException(status_code=404, detail="知识单元不存在")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"code": 200, "data": item}


@app.post("/knowledge-units/{knowledge_unit_id}/publish")
def publish_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "ACTIVE")


@app.post("/knowledge-units/{knowledge_unit_id}/disable")
def disable_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "DISABLED")


@app.post("/knowledge-units/{knowledge_unit_id}/enable")
def enable_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "ACTIVE")


@app.post("/knowledge-units/{knowledge_unit_id}/archive")
def archive_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "ARCHIVED")


@app.post("/knowledge-units/{knowledge_unit_id}/restore")
def restore_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "DISABLED")


@app.delete("/knowledge-units/{knowledge_unit_id}")
def delete_knowledge_unit(knowledge_unit_id: str):
    return _transition_knowledge_unit(knowledge_unit_id, "DELETED")


@app.put("/knowledge-units/{knowledge_unit_id}/permissions")
def update_knowledge_permissions(knowledge_unit_id: str, request: KnowledgePermissionRequest):
    try:
        item = knowledge_unit_store.update_permissions(knowledge_unit_id, request.permissions)
    except KeyError:
        raise HTTPException(status_code=404, detail="知识单元不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"code": 200, "data": item}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app=app,host="0.0.0.0",port=8000) #端口号是固定! 前端页面是写死的 8000
