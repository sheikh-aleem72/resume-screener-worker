import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
# env = os.getenv("ENV", "development")
# load_dotenv(f".env.{env}")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment")

client = genai.Client(api_key=API_KEY)

# list models
models = client.models.list()   # returns model metadata





# def parse_resume_with_gemini(text: str, model_id: str = "models/gemini-2.5-flash") -> dict:
#     response = client.models.generate_content(
#           model=model_id,
#           contents=[{"role": "user", "parts": [{"text": prompt}]}],
#          # you can add max output tokens, temperature etc. in "config" if needed
#        )

