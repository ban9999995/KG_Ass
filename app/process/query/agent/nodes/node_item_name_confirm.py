import json
import sys
import time

from app.shared.runtime.logger import node_log
from app.rag.query.item_name_confirm_service import confirm_item_name
from app.shared.utils.task_utils import add_done_task, add_running_task

@node_log("node_item_name_confirm")  # 节点的进入和执行结束的Info日志
def node_item_name_confirm(state):
    """
    节点功能：确认用户问题中的核心商品名称。
    输入：state['original_query']
    输出：更新 state['item_names']
    """
    # sys._getframe().f_code.co_name -> 获取节点名 node_item_name_confirm
    # state["is_stream"] => 流式响应
    add_running_task(state["session_id"],"node_item_name_confirm", state["is_stream"])  # 记录节点状态 [哪个节点运行中]
    # 调用 rag/query service 层
    state = confirm_item_name(state)  # 调用业务函数
    # 识别完成后写入完成列表，方便前端展示当前节点已结束。
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state  # 结果返回给图


if __name__ == "__main__":
    mock_state = {
        "session_id": "test_session_001",
        "original_query": "HAK 180 烫金机怎么用？",
        "is_stream": False,
    }
    result_state = node_item_name_confirm(mock_state)
    print(result_state)