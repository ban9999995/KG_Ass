from mimetypes import guess_type

f1 = "xx.png"
f2 = "xx.jpg"
f3 = "xx.doc"
f4 = "xx.mp4"

print(guess_type(f1)[0])
print(guess_type(f2))
print(guess_type(f3))  # - > (mimetype,压缩格式)
print(guess_type(f4))