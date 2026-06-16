import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None

def generate_completion(messages, model="google/gemini-2.0-flash-exp:free", temperature=0.7, stream=False):
    """
    Generate completion using OpenRouter API.
    Fully compatible with OpenAI SDK.
    """
    global _client
    
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables.")
        # OpenRouter base URL
        _client = OpenAI(
            api_key=api_key, 
            base_url="https://openrouter.ai/api/v1"
        )
        
    client = _client
    
    # List of FREE models on OpenRouter ordered by SPEED and SMARTNESS
    models_to_try = [
        "google/gemma-4-31b-it:free",              # Fast & Smart (31B)
        "meta-llama/llama-3.3-70b-instruct:free",  # Very Smart (70B) but can be slow
        "meta-llama/llama-3.2-3b-instruct:free",   # Lightning Fast (3B) fallback
        "nousresearch/hermes-3-llama-3.1-405b:free", # Super Smart (405B) fallback
        "qwen/qwen3-next-80b-a3b-instruct:free"    # Great multilingual fallback
    ]
    
    # If the requested model is not in our free list, put it first
    if model not in models_to_try:
        models_to_try.insert(0, model)
    
    try:
        if stream:
            def generate_with_fallback():
                for i, model_name in enumerate(models_to_try):
                    chunks_yielded = 0
                    try:
                        response = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temperature,
                            stream=True,
                            extra_headers={
                                "HTTP-Referer": "https://youtube-search.vercel.app/",
                                "X-Title": "YouTube Islamic Search"
                            }
                        )
                        for chunk in response:
                            if chunk.choices and chunk.choices[0].delta.content:
                                yield chunk.choices[0].delta.content
                                chunks_yielded += 1
                        break # Success!
                    except Exception as e:
                        logger.warning(f"OpenRouter Model {model_name} failed: {e}")
                        if chunks_yielded > 0:
                            raise Exception(f"Stream interrupted midway: {str(e)}")
                        if i == len(models_to_try) - 1:
                            raise
                        continue
            return generate_with_fallback()
        else:
            for i, model_name in enumerate(models_to_try):
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=temperature,
                        stream=False,
                        extra_headers={
                            "HTTP-Referer": "https://youtube-search.vercel.app/",
                            "X-Title": "YouTube Islamic Search"
                        }
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    logger.warning(f"OpenRouter Model {model_name} failed: {e}")
                    if i == len(models_to_try) - 1:
                        raise
                    continue
            
    except Exception as e:
        logger.error(f"OpenRouter API Error: {str(e)}")
        raise ValueError(f"เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI: {str(e)}")
