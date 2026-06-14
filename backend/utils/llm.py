import os
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)

def generate_completion(messages, model="gpt-4o-mini", temperature=0.7, stream=False):
    import google.generativeai as genai
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")
        
    genai.configure(api_key=api_key)
    
    # Convert OpenAI message format to Gemini format
    system_instruction = ""
    gemini_messages = []
    
    for msg in messages:
        if msg["role"] == "system":
            system_instruction += msg["content"] + "\n"
        elif msg["role"] == "user":
            gemini_messages.append({"role": "user", "parts": [msg["content"]]})
        elif msg["role"] == "assistant":
            gemini_messages.append({"role": "model", "parts": [msg["content"]]})
            
    generation_config = genai.types.GenerationConfig(
        temperature=temperature,
    )
    
    try:
        model_instance = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_instruction if system_instruction else None,
            generation_config=generation_config
        )
        
        if stream:
            response = model_instance.generate_content(gemini_messages, stream=True)
            def generate():
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            return generate()
        else:
            response = model_instance.generate_content(gemini_messages)
            return response.text
            
    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        raise ValueError(f"เกิดข้อผิดพลาดจากเซิร์ฟเวอร์ AI: {str(e)}")
