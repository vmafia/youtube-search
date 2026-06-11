import json
import os

json_path = r"C:\Users\hp\Downloads\cookies.json"
txt_path = r"C:\Users\hp\Documents\GitHub\youtube-search\cookies_new.txt"

print(f"Reading JSON from: {json_path}")
if not os.path.exists(json_path):
    print(f"Error: JSON cookie file not found at {json_path}")
    exit(1)

with open(json_path, "r", encoding="utf-8") as f:
    cookies = json.load(f)

lines = [
    "# Netscape HTTP Cookie File",
    "# http://curl.haxx.se/rfc/cookie_spec.html",
    "# This file was converted from JSON automatically",
    ""
]

count = 0
for cookie in cookies:
    domain = cookie.get("domain", "")
    host_only = cookie.get("hostOnly", False)
    
    if not host_only and not domain.startswith("."):
        if not domain.replace(".", "").isdigit() and domain != "localhost":
            domain = "." + domain
            
    subdomains_flag = "FALSE" if host_only else "TRUE"
    path = cookie.get("path", "/")
    secure = "TRUE" if cookie.get("secure", False) else "FALSE"
    
    exp_date = cookie.get("expirationDate")
    if exp_date is None or cookie.get("session", False):
        expiration = "2147483647"
    else:
        expiration = str(int(exp_date))
        
    name = cookie.get("name", "")
    value = cookie.get("value", "")
    
    if not name:
        continue
        
    line = "\t".join([
        domain,
        subdomains_flag,
        path,
        secure,
        expiration,
        name,
        value
    ])
    lines.append(line)
    count += 1

print(f"Prepared {len(lines)} lines (including header) to write.")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Successfully converted {count} cookies from JSON to Netscape format.")
print(f"Saved to: {txt_path}")
print(f"File size on disk right after write: {os.path.getsize(txt_path)} bytes")

with open(txt_path, "r", encoding="utf-8") as f:
    read_lines = f.readlines()
print(f"Read back from {txt_path} right after write: {len(read_lines)} lines")
