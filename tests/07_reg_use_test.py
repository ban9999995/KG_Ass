import re

md_content = "这里有demo(1).png一张图 ![二大爷](images/demo(1).png) 再来一张 ![驴蛋蛋](images/demo(1).png)"
image_name = "demo(1).png"

image_name = re.escape(image_name)

# 查找 image_name图片在md_content中的应用位置
"""
   . 任意一个字符串 
   * 任意数量  
   .* 
   ? 非贪婪匹配
   
   !  -> 非 不是 !
   [] -> 范围 [a-z]
   () -> 聚焦
   
   元数据 -> 不想使用特殊能力 -> 真实值 \
   
   正则中: 1. 真实值 demo(1).png  2.元数据 . * ? -> 特殊含义  \d -> 数字
"""
rep = re.compile(r"\!\[.*?\]\(.*?"+image_name+".*?\)")


# 1. search：全文找【第一个】匹配 → 返回 match 对象
# todo: 匹配内容的包装对象 Match对象 : ![二大爷](images/demo(1).png)  start end
# 找到匹配的第一个数据
match_obj = rep.search(md_content)
print(f"匹配内容:{match_obj.group()} ,匹配的坐标:{match_obj.start()} , {match_obj.end()}")
# 找到匹配的第一个! 从[头]开始匹配
match_first = rep.match(md_content)
print(match_first)
# 找到所有的匹配项
list = rep.finditer(md_content)

for m in list:
    print(f"匹配内容:{m.group()} ,匹配的坐标:{m.start()} , {m.end()}")

print("*" * 100)
# todo: 找到匹配的内容  ![二大爷](images/demo(1).png)
# 找到所有的匹配内容
all_list = rep.findall(md_content)
print(all_list)

# rep = re.compile(r"\!\[.*?\]\((.*?"+image_name+".*?)\)")
# () 和 ?  贪婪匹配
text = "A123B456B"
# 1. 用 .*  → 贪婪（吃到最后）
print(re.findall(r"A(.*)B", text))  # 输出：A123B456B
# 2. 用 .*? → 非贪婪（找到第一个就停）
print(re.findall(r"A(.*?)B", text)) # 输出：A123B