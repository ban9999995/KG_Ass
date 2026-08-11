import re
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from minio import Minio
from minio.datatypes import Object
from minio.deleteobjects import DeleteObject

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import SUPPORTED_IMAGE_EXTENSIONS, SUB_MD_CONTENT_CONTEXT_LENGTH
from app.shared.runtime.logger import logger, step_log
from app.infra.model.model_providers import model_provider
from app.infra.config.providers import infra_config
from app.shared.runtime.load_prompt import load_prompt
import base64
from mimetypes import guess_type

from app.shared.utils.rate_limit_utils import apply_api_rate_limit
from app.infra.minio.ObjectStore import minio_gateway


# 1. 获取参数并且校验(state) -> md_content:str  md_path_obj:Path  images_path_obj:Path
@step_log("validate_data_and_paths")
def validate_data_and_paths(state:ImportGraphState) -> tuple[str,Path,Path]:
    # 1.1 获取请求参数 md_path
    md_path:str = state.get("md_path")
    # 1.2 非空校验 -> 空 -> error
    if not md_path:
        logger.error(f"md_path值为空,无法读取文档内容,业务无法继续,提前终止!!")
        raise ValueError(f"md_path值为空,无法读取文档内容,业务无法继续,提前终止!!")
    # 1.3 md_path转成md_path_obj:Path
    md_path_obj:Path = Path(md_path)
    # 1.4 文件存在性校验 -> is_file() -> 不存在 -> error
    if not md_path_obj.is_file():
        logger.error(f"md_path有地址:{md_path},但是没有真实的文件,业务无法继续,提前终止!!")
        raise FileNotFoundError(f"md_path有地址:{md_path},但是没有真实的文件,业务无法继续,提前终止!!")
    # 1.5 基于md_path_obj读取文件内容 -> md_content -> state
    md_content = md_path_obj.read_text(encoding="utf-8")
    state['md_content'] = md_content
    # 1.6 基于md_path_obj获取images_path_obj对象
    images_dir_obj:Path = md_path_obj.parent / "images"
    # 1.7 返回三个核心参数 ...
    return md_content,md_path_obj,images_dir_obj


#3. 查找images_path_obj每张图片对应的上下文信息(images_path_obj,md_content) -> [(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4]
@step_log("extract_image_context_info")
def extract_image_context_info(images_dir_obj:Path,md_content:str) -> list[tuple[str,Path,tuple[str,str]]]:
    image_context_list:list[tuple[str,Path,tuple[str,str]]] = []
    # 3.1 遍历循环images_path_obj每个文件 for Path in images_path_obj.iterdir() glob rglob
    for file_obj in  images_dir_obj.iterdir():
        # 3.2 检查是不是图片(后缀名判断)
        if file_obj.suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            # 不是图片
            # for -> debug -> 一个节点的内部 -> 循环的不确定  工具类 和 源码包 使用debug
            logger.debug(f"本次处理的:{file_obj}不是一张图片,所以跳过!进行下一次处理!")
            continue
        # 3.3 定义图片对应的正则编译对象 re.compile(r"\!\[.*?\]\(.*?" + re.escape(图片名)+r".*?\)")
        image_name = file_obj.name
        image_re = re.compile(f"\!\[.*?\]\(.*?"+re.escape(image_name)+r".*?\)")
        # 3.4 调用正则编译对象去md_content找到匹配内容 .match [search] finditer findall [图片永远不会重复] -> Match
        image_match: re.Match =  image_re.search(md_content)
        # 3.5 对Match对象进行非空检查,为空 -> 图片没有md_content应用 [下一张图片]
        if not image_match:
            logger.debug(f"本次处理的:{file_obj}是一张图片,但是没有被md_content引用,所以跳过!进行下一次处理!")
            continue
        # 3.6 根据Match获取图片的定位信息 .start() .end()
        start = image_match.start()
        end   = image_match.end()
        # 3.7 上文 = md_content[start-100:start]  [  : )] 下文 = md_content(end,end+100)
        # 注意 SUB_MD_CONTENT_CONTEXT_LENGTH -> config.py定义
        """
          1. SUB_MD_CONTENT_CONTEXT_LENGTH 长度的问题,为啥是100?
          2. 开头和结尾的问题  pre min 0  post max len()
          3. 连续图片的问题阿  晚上作业: 连续图片,跳过图片继续+截取  ![]() ![]() 20 +  80 -> 跳过图片截取100
                                                             ![]() 10 ![]() ![]()40 +  50 -> 跳过图片截取90
                            \!\[.*?\]\(.*?\) -> finditer
        """
        pre_context  = md_content[max(start - SUB_MD_CONTENT_CONTEXT_LENGTH,0):start]
        post_context = md_content[end:min(end + SUB_MD_CONTENT_CONTEXT_LENGTH,len(md_content))]
        # 3.8 拼接个单个元素的原则 (path.name,path,(上,下))  list.append()
        image_context_list.append(
            (
                image_name,file_obj,
                (pre_context,post_context)
            )
        )
    # 3.9 跳出循环,打印日志,返回结果 list
    logger.info(f"图片上下文识别结束,识别图片的长度:{len(image_context_list)},{'images文件夹都是非图片文件!' if len(image_context_list) == 0 else '参考示例:' + str(image_context_list[0]) }")
    return image_context_list


# 4. 调用视觉模型进行图片内容识别([(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4] , 文件名 md_path_obj.stem) -> {图片名:语义 ....}
@step_log("call_vision_summary_images")
def call_vision_summary_images(images_context_list:list[tuple[str,Path,tuple[str,str]]],file_name:str) -> dict[str,str]:
    # 字典
    images_summaries:dict[str,str] = {}
    # 4.1 获取视觉模型对象(infra vision...)
    lv_model = model_provider.vision_model(model_name=infra_config.lm_config.lv_model)
    # 4.2 循环每张图片对应的上下文信息 (图片名,完成地址,(上,下文))
    for image_name,image_path_obj,image_content in images_context_list:
        # 访问限制 不能超过模型每分钟数量 3000 https://help.aliyun.com/zh/model-studio/rate-limit?spm=a2c4g.11186623.help-menu-2400256.d_0_0_4.5740d355MgCFPC
        apply_api_rate_limit(max_requests=3000,window_seconds=60)
        # 4.3 加载和拼接对应的提示词 load_prompts("image_summary",root_folder=stem,image_content=(上,下文))
        summary_prompt_text:str =  load_prompt("image_summary",root_folder=file_name,image_content=image_content)
        # 4.4 提示词封装成Message HumanMessage(content=提示词)
        image_base64_data:str = base64.b64encode(image_path_obj.read_bytes()).decode(encoding="utf-8")
        image_mimetype:str    = guess_type(image_name)[0]
        message = HumanMessage(
            content  = [
                {"type":"text","text":summary_prompt_text},
                {"type":"image_url","image_url":{"url":f"data:{image_mimetype};base64,{image_base64_data}"}}
            ]
        )
        # 4.5 封装一个调用 chains = 模型 | StrOutputParser() / JsonOutputParser()
        chains = lv_model | StrOutputParser()
        # 4.6 调用模型的链 chains.invoke([human_message]) -> 结果要的字符串     模型.invoke([]) -> response . content
        image_summary:str =  chains.invoke([message])
        # 4.7 存储图片的函数  字典[图片名] = summary 结果要的字符串
        images_summaries[image_name] = image_summary
        logger.debug(f"本次识别的图片名:{image_name},识别的语义为:{image_summary}")
    # 4.8 打印日志 返回结果 return 字典
    logger.info(f"完成图片的语义识别,本次识别的数量为:{len(images_summaries)}")
    return images_summaries

# 5. 调用minio将图片传递到文件服务器([(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4]) -> {图片名:http...}
@step_log("upload_to_minio_return_url")
def upload_to_minio_return_url(images_context_list:list[tuple[str,Path,tuple[str,str]]], file_name:str) -> dict[str,str]:
    images_url:dict[str,str] = {}
    # 5.1 获取minio的客户端对象 infra.函数 -> @property
    minio_client:Minio = minio_gateway.minio
    # 5.2 先根据固定的前缀查询存不存在图片  list_objects(桶名,前缀="图片固定的前缀infra/文件夹名") []
    # https://www.minio.org.cn/docs/minio/linux/developers/python/API.html#list_objects           一定要好好看官方文档 连一个/都不能查! 切记
    select_object_list:list[Object] =  minio_client.list_objects(
        bucket_name=minio_gateway.bucket_name,
        #  images_prefix = / 所以查不到!  prefix = 不能使用 /  后面+不+都行
        prefix=minio_gateway.images_prefix[1:] + "/" + file_name,
        recursive=True
    )
    delete_object_list:list[DeleteObject] =  [DeleteObject(obj.object_name) for obj in select_object_list]
    if delete_object_list:
        logger.info(f"{file_name}对应的文件之前存储过图片!数量:{len(delete_object_list)},先清空!再上传!!")
        # 5.3 如果当前文件夹存在图片,先删除 remove_objects(桶名,DeleteOject)
        # https://www.minio.org.cn/docs/minio/linux/developers/python/API.html#remove_objects
        errors = minio_client.remove_objects(
           bucket_name=minio_gateway.bucket_name,
            delete_object_list=delete_object_list
        )
        for error in errors:
            logger.debug(f"图片处理异常:{error}")
    # 5.4 循环处理上下文件列表,获取每张图片信息 (图片名,地址,_)
    for image_name,image_path_obj,_ in images_context_list:
        try:
            # 5.5 minio中上传文件 fput_object [考虑上传minio报错的问题,不能因为一张图片的报错,影响整个业务]  for try...
            # 桶名 --> 以下全是object_name
            #   /upload-images
            #       /文件名
            #           /图片名
            object_name:str = minio_gateway.images_prefix + "/" + file_name + "/" + image_name
            minio_client.fput_object(
                bucket_name=minio_gateway.bucket_name,
                object_name=object_name,
                file_path=str(image_path_obj),
                content_type=guess_type(image_name)[0]
            )
            # https://www.minio.org.cn/docs/minio/linux/developers/python/API.html#fput_object
            # 5.6 拼接每张图片对应的地址 infra (object_name -> /固定的图片前缀/文件夹名/文件名) -> url
            image_url:str = minio_gateway.build_image_url(object_name=object_name)
            # 5.7 记录当前图片对应的地址 {[图片名],图片地址}
            images_url[image_name] = image_url
            logger.debug(f"{image_name}已经完成上传,对应地址为:{image_url}")
        except Exception as e:
            logger.warning(f"{image_name}上传失败,跳过,继续下一张图片处理!")
            continue
    # 5.8 返回字典(图片名|图片地址) 打印日志
    return images_url



# 6. 使用正则进行md_content内容的替换(md_content,{图片名:语义 ....},{图片名:http...}) -> 新的 md_content
@step_log("replace_old_md_content")
def replace_old_md_content(md_content:str,images_summaries:dict[str,str],images_url:dict[str,str]) -> str:
    # 6.1 循环 图片名,网络地址  {图片名:网络地址}.items()
    for image_name,image_summary in  images_summaries.items():
        # 6.2 根据 图片名获取语义描述 图片名 / 语义 / 地址
        image_url:str = images_url.get(image_name)
        # 6.3 编译一个替换正则对象 ![.*?](.*? image_name .*?) 编译后的正则对象
        # ![](./image_name) -> ![语义](http...)
        image_re = re.compile(r"\!\[.*?\]\(.*?"+re.escape(image_name)+r".*?\)")
        # 6.4 进行正则对象  md_content =   编译后的正则对象 ![](./xxxxx.jpg) .sub( 要替换入的新的内容 "![语义](网络地址)" , 在哪个内容上替换 md_content )
        # f"![{image_summary}]({image_url})"  /
        """
            参数1: 本意不是正则表达式,就是要替换入的字符串 所以出现特殊字符(元字符)  ![语义](http..)
                  替换有个特殊符号 \ 数字 -> 分组替换  xx\2xx.png
                  方式1: 传入字符串  xx\2xx.png -> 报错
                  方式2: 匿名函数 lambda  lambda _ : ![{image_summary}]({image_url}) -> 直接调用函数,将返回值不会做任何处理! \1 
            替换后的字符串 md_content [34]= sub(参数1:要替换入的字符串,参数2:在哪个字符串中进行查找和替换 md_content[234]) -> 内容替换
        
        """
        md_content =  image_re.sub(lambda _ : f"![{image_summary}]({image_url})",md_content)
    # 6.5 循环结束,替换完毕,return md_content
    return md_content

# 7. 对新的md_content的进行内容备份(md_content,md_path_obj) -> new_md_path地址
@step_log("backup_new_md_content")
def backup_new_md_content(new_md_content:str,md_path_obj:Path) -> Path:
    # 7.1 获取新的md_path的目标地址 new_md_path_obj:Path = md_path_obj.with_name(f"{md_path_obj.stem}_new.md")
    new_md_path_obj:Path = md_path_obj.with_name(f"{md_path_obj.stem}_new.md")
    # 7.2 将内容写到新的地址 new_md_path_obj
    new_md_path_obj.write_text(data=new_md_content,encoding="utf-8")
    # 7.3 返回新的地址 return
    return new_md_path_obj

@step_log("enrich_markdown_images")
def enrich_markdown_images(state: ImportGraphState) -> ImportGraphState:
    # 1. 获取参数并且校验(state) -> md_content:str  md_path_obj:Path  images_path_obj:Path
    md_content,md_path_obj,images_dir_obj = validate_data_and_paths(state)
    # 2. 图片的非空内容校验,为空提前终止,进行下一个节点images_path_obj [不需要封装成函数]
    if (not images_dir_obj.is_dir()) or (not list(images_dir_obj.iterdir())):
        # 为空,或者图片
        logger.info(f"{md_path_obj}:md文件,没有图片,无需图片处理,直接跳转到下一个节点!")
        return state
    # 3. 查找images_path_obj每张图片对应的上下文信息(images_path_obj,md_content) -> [(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4]
    images_context_list:list[tuple[str,Path,tuple[str,str]]] = extract_image_context_info(images_dir_obj,md_content)
    if not images_context_list:
        # 为空,或者图片
        logger.info(f"{md_path_obj}:md文件,images文件夹不为空,但是没有图片,无需图片处理,直接跳转到下一个节点!")
        return state
    # 4. 调用视觉模型进行图片内容识别([(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4] , 文件名 md_path_obj.stem) -> {图片名:语义 ....}
    images_summaries:dict[str,str] = call_vision_summary_images(images_context_list,md_path_obj.stem)
    # 5. 调用minio将图片传递到文件服务器([(图片名.name,图片的完整地址:str/Path,(上文,上文)),2,3,4]) -> {图片名:http...}
    images_url:dict[str,str] =  upload_to_minio_return_url(images_context_list,md_path_obj.stem)
    # 6. 使用正则进行md_content内容的替换(md_content,{图片名:语义 ....},{图片名:http...}) -> 新的 md_content
    new_md_content:str = replace_old_md_content(md_content,images_summaries,images_url)
    # 7. 进行new_md_content备份
    new_md_path_obj:Path = backup_new_md_content(new_md_content,md_path_obj)
    # 8. 更新state 并且返回即可
    # 8.1 更新state md_content / md_path
    state['md_content'] = new_md_content
    state['md_path'] = str(new_md_path_obj)
    # 8.2 返回state
    return state