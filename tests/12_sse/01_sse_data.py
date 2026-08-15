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

    # 为啥是 生成器函数 ?
    # 生成器函数: 没办法一起返回,一部分一部分返回! llm.stream()
    async def generator():
        # 模拟流式结果 1秒 返回一个数字 大概返回10秒
        for index in range(10):
            # yield f"第{index}个结果!" -> 浏览器接收没问题
            # yield f"data: 第{index}个结果!\n\n"
            yield f"data: 第{index}个结果!\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generator(),media_type="text/event-stream")


@app.get("/html")
def return_html():
    html_path_obj:Path = Path(__file__).parent / "01_sse_data.html"
    return FileResponse(
        path = str(html_path_obj),
        media_type=guess_type(html_path_obj.name)[0]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=7777)





