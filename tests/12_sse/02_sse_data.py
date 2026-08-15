import asyncio

from fastapi import FastAPI
from fastapi.responses import StreamingResponse , FileResponse
from pathlib import Path
from mimetypes import guess_type



app = FastAPI()
# 需求1: 后端单纯使用流式响应,返回多段数据!!
# 接口 流式响应的接口
@app.get("/stream")
async def return_stream():

    # 返回两种事件类型! 1. 下载的进度事件 带有下载的进度 [processing]  2. 下载完成事件 下载完成 [completed]

    async def generator():
        # 模拟流式结果 1秒 返回一个数字 大概返回10秒
        for index in range(101):
            yield f"event: processing\n"
            yield f"data: {index}\n\n"
            await asyncio.sleep(0.1)
        yield f"event: completed\n"
        yield f"data: <font color='#fb5832'>下载完成</font>\n\n"

    return StreamingResponse(generator(),media_type="text/event-stream")

@app.get("/html")
def return_html():
    html_path_obj:Path = Path(__file__).parent / "02_sse_data.html"
    return FileResponse(
        path = str(html_path_obj),
        media_type=guess_type(html_path_obj.name)[0]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=8888)





