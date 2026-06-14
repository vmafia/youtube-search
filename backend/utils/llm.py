import os
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)

_client = None

def generate_completion(messages, model="gpt-4o-mini", temperature=0.7, stream=False):
    from google import genai
    from google.genai import types
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    global _client
    
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        _client = genai.Client(api_key=api_key)
        
    client = _client
    
    # Convert OpenAI message format to Gemini format
    system_instruction = ""
    gemini_messages = []
    
    for msg in messages:
        if msg["role"] == "system":
            system_instruction += msg["content"] + "\n"
        elif msg["role"] == "user":
            gemini_messages.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
        elif msg["role"] == "assistant":
            gemini_messages.append(types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])]))
            
    try:
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction if system_instruction else None
        )
        
        if stream:
            response = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=gemini_messages,
                config=config
            )
            def generate():
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            return generate()
        else:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=gemini_messages,
                config=config
            )
            return response.text
            
    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        raise ValueError(f"เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI: {str(e)}")
