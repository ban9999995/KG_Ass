import base64
from app.shared.runtime.logger import logger,PROJECT_ROOT


# ====================== 【你只需要改这里】填写你的图片路径 ======================
IMAGE_PATH = PROJECT_ROOT / "output" / "mv.png"  # 改成你的图片：a.jpg / logo.png 等
COPY_IMAGE_PATH = PROJECT_ROOT / "output" / "mv_copy.png"  # 改成你的图片：a.jpg / logo.png 等
# ==============================================================================

# -------------------- 1. 图片 → Base64 字符串（编码） --------------------
print("正在把图片转 Base64...")

base64_string = base64.b64encode(IMAGE_PATH.read_bytes()).decode("utf-8")
print("✅ 图片转 Base64 完成！")
print("Base64 字符串前50个字符：", base64_string[:50], "...")


# -------------------- 2. Base64 字符串 → 还原成图片（解码） --------------------
print("\n正在把 Base64 转回图片...")
image_binary = base64.b64decode(base64_string)
COPY_IMAGE_PATH.write_bytes(data = image_binary)
