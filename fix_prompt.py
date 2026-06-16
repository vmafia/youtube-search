import os

file_path = r'backend/app.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_prompt = '''  5. หากมีการอ้างอิงวิดีโอ ให้บอกด้วยว่าพบในวิดีโอ ID ใด (เช่น วิดีโอ id xyz นาทีที่ 12:30)'''

new_prompt = '''  5. ห้ามใช้ Markdown Formatting (เช่น ** หรือ * หรือ #) ให้ใช้การเว้นวรรคหรือขึ้นบรรทัดใหม่ธรรมดาเพื่อให้มนุษย์อ่านง่ายที่สุด
  6. ห้ามสร้างลิงก์อ้างอิงวิดีโอหรือแนบรูปภาพใดๆ เองเด็ดขาด เพราะระบบมี UI แนบการ์ดวิดีโอให้ผู้ใช้โดยอัตโนมัติอยู่แล้วใต้ข้อความของคุณ'''

content = content.replace(old_prompt, new_prompt)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated system prompt in app.py')
