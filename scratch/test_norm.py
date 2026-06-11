import re

def normalize_text(text: str) -> str:
    text = text.lower().strip()
    
    # Strip common marks
    text = re.sub(r"[\u0e4c\u0e3a\u0e4e\u0e47]", "", text)
    
    # Consonant consolidation
    text = text.replace("ศ", "ส").replace("ษ", "ส").replace("ซ", "ส")
    text = text.replace("ฑ", "ท").replace("ฒ", "ท").replace("ธ", "ท").replace("ถ", "ท").replace("ฐ", "ท")
    text = text.replace("ณ", "น")
    text = text.replace("ภ", "พ")
    
    # Vowel consolidation (ลอฮ์, เลาะฮ์, ลอฮฺ)
    text = re.sub(r"เลาะ", "ลอ", text)
    text = re.sub(r"ลอฮ", "ลอ", text)
    
    text = re.sub(r"[^\u0e00-\u0e7fa-zA-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

examples = [
    ("อับดุลเลาะฮ์", "อับดุลลอฮ์"),
    ("ซอฮาบะฮ์", "ศอฮาบะฮฺ"),
    ("อุลามาอฺ", "อุลามาอ์"),
    ("สะลัฟ", "ซะลัฟ"),
    ("หะดีษ", "ฮาดิษ")
]

for ex1, ex2 in examples:
    n1 = normalize_text(ex1)
    n2 = normalize_text(ex2)
    print(f"'{ex1}' -> '{n1}' | '{ex2}' -> '{n2}' | Matches: {n1 == n2}")
