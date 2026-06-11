import os
for key in os.environ:
    if "API" in key or "KEY" in key or "GOOGLE" in key or "GEMINI" in key or "OPENAI" in key:
        print(f"{key}: {'*' * len(os.environ[key])}")
