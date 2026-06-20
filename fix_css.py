import io
with io.open('frontend/src/index.css', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 1. Duplicate font import
lines = content.split('\n')
seen_imports = set()
new_lines = []
for line in lines:
    if line.startswith('@import url'):
        if line in seen_imports:
            continue
        seen_imports.add(line)
    new_lines.append(line)
content = '\n'.join(new_lines)

# 2. Add --teal-hover
if '--teal-hover' not in content:
    content = content.replace('--teal: #0d9488;', '--teal: #0d9488;\n  --teal-hover: #0f766e;')

# 3. Add filter-pill classes if missing
if '.filter-pill' not in content:
    content += "\n\n.filter-pill {\n  padding: 0.5rem 1rem;\n  border-radius: 9999px;\n  background-color: var(--bg2);\n  color: var(--text);\n  border: 1px solid var(--br);\n  cursor: pointer;\n  transition: all 0.2s;\n}\n.filter-pill:hover {\n  background-color: var(--bg3);\n}\n.filter-pill.active {\n  background-color: var(--teal);\n  color: white;\n  border-color: var(--teal);\n}\n"

with io.open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(content)
