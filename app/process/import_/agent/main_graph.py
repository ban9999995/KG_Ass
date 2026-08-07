from langgraph.constants import END
from langgraph.graph import StateGraph
from app.process.import_.agent.state import ImportGraphState
from app.process.import_.agent.nodes.node_entry import node_entry
from app.process.import_.agent.nodes.node_pdf_to_md import node_pdf_to_md
from app.process.import_.agent.nodes.node_md_img import node_md_img
from app.process.import_.agent.nodes.node_document_split import node_document_split
from app.process.import_.agent.nodes.node_item_name_recognition import node_item_name_recognition
from app.process.import_.agent.nodes.node_bge_embedding import node_bge_embedding
from app.process.import_.agent.nodes.node_import_milvus import node_import_milvus
from app.shared.runtime.logger import logger

# 1. 创建图的构建对象 StateGraph(state)
import_graph_builder = StateGraph(ImportGraphState)

# 2. 添加图节点
import_graph_builder.add_node(node_entry)
import_graph_builder.add_node(node_pdf_to_md)
import_graph_builder.add_node(node_md_img)
import_graph_builder.add_node(node_document_split)
import_graph_builder.add_node(node_item_name_recognition)
import_graph_builder.add_node(node_bge_embedding)
import_graph_builder.add_node(node_import_milvus)

# 3. 添加图的边
#import_graph_builder.add_edge(START,"node_entry")
import_graph_builder.set_entry_point("node_entry")


# 条件边的路由函数,允许我们使用全局state
def after_node_entry(state:ImportGraphState)-> str:
    # 条件边! 如果是pdf -> node_pdf_to_md 如果是md -> node_md_img  如果都不是 -> END
    if state.get("is_pdf_read_enabled",False):
        # 位置 / 级别 / 内容 有依据 + 结果!!
        logger.info(f"传入的文件地址:{state.get('local_file_path')},文件类型为pdf,跳转到node_pdf_to_md节点!")
        return "node_pdf_to_md"
    if state.get("is_md_read_enabled",False):
        logger.info(f"传入的文件地址:{state.get('local_file_path')},文件类型为md,跳转到node_md_img节点!")
        return "node_md_img"
    else:
        logger.info(f"传入的文件地址:{state.get('local_file_path')},文件既不是md又不是pdf,无法处理,直接跳到END节点!")
        return END
"""
  条件边添加:
    参数1: 起始节点
    参数2: 路由函数 (state -> 判断 -> 目标节点名)
    参数3: path_map -> dict -> 场景1: 静态测试必须显示说明条件路由函数返回值对应的目标节点  key[返回的值]:value [目标节点]
                              场景2: 路由函数返回的值不等于节点名,path_map指定! 

"""
import_graph_builder.add_conditional_edges(
    "node_entry",
        after_node_entry,
    {
        "node_pdf_to_md":"node_pdf_to_md",
        "node_md_img":"node_md_img",
        END:END
    }
)

# 静态边

import_graph_builder.add_edge("node_pdf_to_md","node_md_img")
import_graph_builder.add_edge("node_md_img","node_document_split")
import_graph_builder.add_edge("node_document_split","node_item_name_recognition")
import_graph_builder.add_edge("node_item_name_recognition","node_bge_embedding")
import_graph_builder.add_edge("node_bge_embedding","node_import_milvus")
import_graph_builder.add_edge("node_import_milvus",END)

# 4. 编译对象即可
import_graph_app = import_graph_builder.compile()