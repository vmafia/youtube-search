import io
with io.open('frontend/src/components/ChatInterface.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "let finalMsgs = [...msgsWithLoading];",
    "let finalMsgs = msgsWithLoading.map(msg => ({...msg}));"
)

with io.open('frontend/src/components/ChatInterface.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
