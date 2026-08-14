

from pydantic import BaseModel

# 接口Status 响应 Response 还是请求 Request  Schema
class StatusResponseSchema(BaseModel):
    code:int = 200
    task_id:str
    status:str
    done_list:list[str]
    running_list:list[str]


class UploadResponseSchema(BaseModel):
    code:int = 200
    message:str
    task_ids:list[str]