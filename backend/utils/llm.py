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
    
    # Defense-in-depth: Only allow the first message to be 'system' (constructed by backend)
    # and strip any subsequent system messages.
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            if i == 0:
                system_instruction += content + "\n"
            else:
                logger.warning("Dropped unexpected system message in generate_completion history.")
        elif role in ["user", "assistant", "model"]:
            gemini_role = "user" if role == "user" else "model"
            # If the last message is of the same role, merge them to avoid alternating error
            if gemini_messages and gemini_messages[-1].role == gemini_role:
                gemini_messages[-1].parts[0].text += "\n\n" + content
            else:
                gemini_messages.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)]))
                
    # Gemini requires the conversation to START with a user message.
    # If due to truncation or history the first message is 'model', drop it.
    while gemini_messages and gemini_messages[0].role == "model":
        gemini_messages.pop(0)
            
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
