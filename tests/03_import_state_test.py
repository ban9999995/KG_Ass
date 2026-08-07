from app.shared.runtime.logger import logger
from app.process.import_.agent.state import create_default_state,get_default_state,ImportGraphState

# 1. 创建一个修改 local_file_path / task_id state
state1 = create_default_state(local_file_path="./xxx.pdf",task_id="007")
logger.info(state1)

import json
# json.dumps   json.dump   ->  python的数据对象 -> 转成 -> json  s -> json字符串 不带s -> 文件处理 chunk.json
# json.loads   json.load   ->  json字符串 / .json -> 转成 -> python的字典对象等  s -> json字符串 不带s -> 文件处理 chunk.json

state2 = create_default_state(local_file_path="./xxx.md")
logger.info(f"state2 = \n {json.dumps(state2,indent=4,ensure_ascii=False)}")
