import os
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)

def generate_completion(messages, model="gpt-4o-mini", temperature=0.7):
    # Default to UncleDev's API if no OPENAI_BASE_URL is provided, or fallback to standard OpenAI
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    if base_url.endswith("/chat") or base_url.endswith("/chat/completions"):
        url = base_url
    else:
        url = f"{base_url}/chat/completions"
        
    api_key = os.environ.get("UNCLEDEV_API_KEY") or os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("API Key not found. Please set UNCLEDEV_API_KEY or OPENAI_API_KEY.")
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    req = urllib.request.Request(url, headers=headers, data=json.dumps(data).encode("utf-8"))
    
    try:
        # In case the custom API endpoint has SSL issues
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, context=ctx) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"LLM API HTTPError {e.code}: {error_body}")
        # Return a fallback message if API fails, so the app doesn't crash completely
        if e.code == 403 or e.code == 401:
            return "ขออภัยครับ API Key ไม่ถูกต้อง หรือไม่มีสิทธิ์เข้าถึงโมเดลนี้"
        elif e.code == 404:
            return "ขออภัยครับ ไม่พบ URL ของ API (404 Not Found) โปรดตรวจสอบ OPENAI_BASE_URL"
        elif e.code == 307:
             return "ขออภัยครับ API มีการ Redirect (307) อาจจะตั้งค่า Endpoint ผิด"
        return f"ขออภัยครับ เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI: {e.code}"
    except Exception as e:
        logger.error(f"LLM API Error: {str(e)}")
        return "ขออภัยครับ ไม่สามารถเชื่อมต่อกับ AI ได้ในขณะนี้"
