import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    client = genai.Client(api_key=api_key)
    try:
        models = client.models.list()
        print("Available models:")
        for m in models:
            if "gemini" in m.name.lower() or "flash" in m.name.lower():
                print(m.name)
    except Exception as e:
        print(f"Error: {e}")
else:
    print("No API key")
