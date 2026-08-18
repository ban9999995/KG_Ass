from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import HYBRID_SEARCH_LIMIT_NUMBER
from app.shared.runtime.logger import logger, step_log
from agents.mcp import MCPServerStreamableHttp
from app.infra.config.providers import infra_config
import asyncio
import json

# 1. 获取和校验参数
@step_log("get_data_and_validate")
def get_data_and_validate(state:QueryGraphState) -> str:
    rewritten_query = state.get("rewritten_query")
    if  not rewritten_query :
        logger.info(f"rewritten_query为空,业务无法继续,提前终止!!")
        raise ValueError(f"rewritten_query为空,业务无法继续,提前终止!!")
    return rewritten_query

# 2. 使用重写问题进行联网搜索
@step_log("web_search_bailian_mcp")
async def web_search_bailian_mcp(rewritten_query:str):
   # openai的mcp服务
   # https://openai.github.io/openai-agents-python/mcp/#2-streamable-http-mcp-servers
   # 1.连接mcp服务
   async with MCPServerStreamableHttp(
           name="bailian web search",
           params={
               "url": infra_config.mcp_config.mcp_base_url,
               "headers": {"Authorization": f"Bearer {infra_config.mcp_config.api_key}"},
               "timeout": 30,
           },
           cache_tools_list=True,
           max_retry_attempts=3,
   ) as server:
        # 2. 获取工具列表
        tool_list = await server.list_tools()
        logger.debug(f"查询到当前服务下的工具列表:{tool_list}")
        # 3. 调用工具列表
        result = await server.call_tool(
            tool_name="bailian_web_search",
            arguments={
                "query":rewritten_query,
                "count":HYBRID_SEARCH_LIMIT_NUMBER
            }
        )
        logger.debug(f"调用bailian_web_search工具,搜索:{rewritten_query},对应结果:{result}")
        return result

#  3. 搜索结果的处理和格式化
#        4. 返回结果即可

@step_log("search_by_web")
def search_by_web(state: QueryGraphState) -> QueryGraphState:
    """
    网络搜索服务：
    1. 通过 MCP 协议异步调用百炼联网搜索接口
    2. 将用户的查询转化为实时的、结构化的网络搜索结果
    3. 包含标题、链接和摘要
    4. 回写 web_search_docs
    """
    # 1.获取并校验参数
    rewritten_query:str = get_data_and_validate(state)
    # 2.调用mcp服务查询结果
    result = asyncio.run(web_search_bailian_mcp(rewritten_query))
    # 3.结果处理
    result_json:str = result.content[0].text
    result_dict:dict = json.loads(result_json)
    # snippet -> content  title -> title  url -> 引用地址 | 图片
    web_search_docs_mcp:list[dict] = result_dict.get("pages",[])

    web_search_docs:list[dict] = [
        {
            "content" : item.get("snippet",""),
            "title"   : item.get("title",""),
            "url"     : item.get("url",""),
            "type"    : "web"
        }
        for item in web_search_docs_mcp
    ]

    logger.info(f"基于:{rewritten_query}问题,进行联网搜索,获取的答案为:{web_search_docs}")

    """
    {"pages":
       [
         {"snippet":"电池下面 添加到", -> content 
          "hostname":"无",
          "hostlogo":"https://img.alicdn.com/imgextra/i2/O1CN01cuA6Dw1WCvM1zP1YK_!!6000000002753-73-tps-16-16.ico",
          "title":"HP Color LaserJet Pro M180-M181 多功能打印机系列 - 故障排除 | HP® 支持",  -> title
          "url":"http://www.support.hp.com/cn-zh/product/details/hp-color-laserjet-pro-m180-m181-mu
          ltifunction-printer-series/14135030"}, -> 图片或者引用网址
          {"snippet":"HP客户支持网站暂时无法访问。我们对带来的不便表示抱歉。请稍后再试。","hostname":"无","hostlogo":"https://img.alicdn.com/imgextra/i2/O1CN01cuA6Dw1WCvM1zP1YK_!!6000000002753-73-tps-16-16.ico","title":"HP Designjet 500/800 系列打印机 - 装载纸张和卷纸介质","url":"https://www.support.hp.com/cn-zh/document/c00371616"},{"snippet":"彩色打印机 本产品支持符合本用户指南规定的多种纸张和其它打印介质。不能控制它们的质量。纸张虽符合本用户指南中的全部规格但打印效果仍不能令人满意的情况也是有可能发生的。无法控制的不确定因素造成的。警告:使用不符合 hp 规格的纸张或打印介质可能造成产品故障,需要进行维修。这种维修不包括在 hp 的担保或服务协议之内。本产品支持在特殊介质上打印。请遵循以下准则以获得满意的结果。使用特殊纸张或打印介质时,请务必在打印机驱动程序中设置类型和尺寸,以获得最佳效果。 警告:hp laserjet 使用热凝器将干碳粉颗粒以十分精确的墨点形式附着在纸张上。hp 激光纸设计为可承受这种极热环境。使用喷墨纸会损坏产品。 正确做法 错误做法 信封 信封应平整存储。 使用接缝延伸到信封角的信封。 使用经核准可用于激光打印机的可揭下的不干胶封条。仅使用未暴露衬纸的标签。 使用平整的标签。仅使用整张的标签。","hostname":"无","hostlogo":"https://img.alicdn.com/imgextra/i2/O1CN01cuA6Dw1WCvM1zP1YK_!!6000000002753-73-tps-16-16.ico","title":"HP LaserJet Enterprise 500 M551 彩色打印机 - 了解如何使用纸张","url":"https://h22207.www2.hp.com/cn-zh/document/c03039056"},{"snippet":"1.1手册适用范围与版本控制 本手册严格限定于印刷企业内部的标准化作业流程,涵盖从设计提交,制版印刷到成品交付的全生命周期管理,确保所有环节均遵循统一的技术标准.适用范围明确排除外部第三方非授权设计作品及实验性打样阶段,所有正式出版物,包装物料及宣传品均须纳入本手册执行范围. 手册版本采用202x-yy-zz格式,其中yy代表年份,zz代表修正迭代次数,任何修订均需在修订版前言中注明生效日期及适用范围变更点.版本号更新时,需同步调整配套《色彩管理操作指南》及《文件传输模板》中的参数设置,确保版本间数据迁移的一致性.当产品材质或印刷工艺发生实质性变更(如纸张克重从80g增至100g)时,必须重新评估并更新手册中的关键参数章节. 所有印刷厂,设计部及质检部门须定期对照手册核对实际作业数据,发现偏差时需立即启动《异常处理流程》进行修正. 1.2设计原则与核心规范 设计必须遵循\"最小化冗余\"原则,避免不必要的装饰元素,确保单页内容在30秒内完成阅读并理解核心信息.色彩应用须严格区分\"主色调\"与\"辅助色\",主色调占比不超过30%,辅助色仅用于强调或点缀,严禁大面积色块覆盖背景. 字体排印需严格执行\"字号层级化\"规范,正文字号不小于12pt,标题字号不小于18pt,行距不小于1.5倍行高以保证可读性.图文布局必须保证\"图文互斥\"风险最小化,避免文字遮挡关键图像细节或图像模糊导致文字难以辨认.色彩转换需考虑\"屏幕与实物色差\",设计稿中的rgb数值需提前输入色彩管理系统,并匹配目标印刷机的icc配置文件. 所有设计规范须符合iso15616印刷色彩标准,确保色域覆盖率达到98%以上,避免使用超出设备能力的颜色. 1.3色彩管理基础理论 色彩空间转换是色彩管理的核心,设计稿rgb值必须精确转换为cmyk值,转换比例需依据印刷厂设备特性进行校准.色彩匹配模型(如cmyk-xyz或lab)用于量化色相,彩度及明度的差异,确保不同设备输出的颜色视觉效果一致. pantone色号(pantonespotcolor)作为印刷专用色彩标准,常用于品牌logo及关键标识,其颜色值不可用cmyk近似替代.色彩偏差(colordeviation)需控制在±2个色度单位以内,超出该范围需通过工艺调整(如墨量增减,网点密度调整)进行修正.白平衡(whitebalance)是色彩一致性的基石,所有文件提交前必须在标准光源(d50)下完成三原色及中性灰的校色. 色彩管理需贯穿设计,制版,印刷及后期加工全流程,任何环节的色差累积均可能导致最终产品不符合客户验收标准. 1.4文件传输与协作标准","hostname":"无","hostlogo":"http://t8.baidu.com/it/u=3027949672,2003644166&fm=195&app=88&f=JPEG?w=200&h=200&s=76D1A8764C706C920AEEFAEE0200501D","title":"印刷设计规范与色彩管理手册.docx 34页VIP","url":"https://m.book118.com/html/2026/0606/7145115125011120.shtm"},{"snippet":"HP客户支持网站暂时无法访问。我们对带来的不便表示抱歉。请稍后再试。","hostname":"无","hostlogo":"https://img.alicdn.com/imgextra/i2/O1CN01cuA6Dw1WCvM1zP1YK_!!6000000002753-73-tps-16-16.ico","title":"HP LaserJet Pro 500 color MFP M570 - 装入纸盘 1","url":"https://h22207.www2.hp.com/cn-zh/document/c03491767"}],"request_id":"68756abf-e41a-99dd-bea3-b35cd75b789a","tools":[],"status":0}

    
    """
    state['web_search_docs'] = web_search_docs
    return state