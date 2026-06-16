import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None

def generate_completion(messages, model="deepseek-chat", temperature=0.7, stream=False):
    """
    Generate completion using DeepSeek API.
    Fully compatible with OpenAI SDK.
    """
    global _client
    
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment variables.")
        # DeepSeek base URL
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
    client = _client
    
    try:
        # DeepSeek (OpenAI compatible) handles messages directly without needing role merging
        if stream:
            def generate():
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            return generate()
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=False
            )
            return response.choices[0].message.content
            
    except Exception as e:
        logger.error(f"DeepSeek API Error: {str(e)}")
        raise ValueError(f"เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI: {str(e)}")
