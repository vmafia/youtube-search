import os

content = open('backend/utils/search.py', 'r', encoding='utf-8').read()

old_loop = '''    for item in transcript:
        original_text = item.get("text", "")
        # Use precomputed norm_text if available, else compute on the fly
        norm_text = item.get("norm_text")
        if not norm_text:
            norm_text = normalize_text(original_text)
            
        if not norm_text:
            continue'''

new_loop = '''    for i, item in enumerate(transcript):
        original_text = item.get("text", "")
        # Use precomputed norm_text if available, else compute on the fly
        norm_text = item.get("norm_text")
        if not norm_text:
            norm_text = normalize_text(original_text)
            
        if not norm_text:
            continue
            
        # Join with next segment to catch phrases split across subtitle lines
        next_text = ""
        if i + 1 < len(transcript):
            next_item = transcript[i+1]
            next_text = next_item.get("norm_text")
            if not next_text:
                next_text = normalize_text(next_item.get("text", ""))
                
        combined_text = norm_text + " " + next_text'''

# also modify where it checks norm_text to check combined_text instead where appropriate?
# Actually, if we just set norm_text = combined_text for the sake of the query search!
# But wait, if we match combined_text, we return `item`. That's fine!

new_loop_2 = '''    for i, item in enumerate(transcript):
        original_text = item.get("text", "")
        # Use precomputed norm_text if available, else compute on the fly
        norm_text = item.get("norm_text")
        if not norm_text:
            norm_text = normalize_text(original_text)
            
        if not norm_text:
            continue
            
        # To catch phrases split across subtitle lines, combine with next line
        next_text = ""
        if i + 1 < len(transcript):
            next_item = transcript[i+1]
            next_text = next_item.get("norm_text") or normalize_text(next_item.get("text", ""))
                
        searchable_text = norm_text + " " + next_text'''

content = content.replace(old_loop, new_loop_2)
content = content.replace('if len(norm_text) < len(norm_query) * 0.6:', 'if len(searchable_text) < len(norm_query) * 0.6:')
content = content.replace('if norm_query in norm_text:', 'if norm_query in searchable_text:')
content = content.replace('term_score = fuzz.partial_ratio(norm_query, norm_text)', 'term_score = fuzz.partial_ratio(norm_query, searchable_text)')

with open('backend/utils/search.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated search.py successfully.")
