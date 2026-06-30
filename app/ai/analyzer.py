import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment")

client = genai.Client(api_key=API_KEY)

# list models
models = client.models.list()   # returns model metadata


def build_analysis_prompt(parsed_resume: dict, job_desc: dict) -> str:
    return f"""
    You are an expert HR and AI-based Resume Analyzer.

    Compare the following candidate resume with the given job description
    and generate a JSON result that includes:
    {{
    "score": number (0-100),
    "fitLevel": "High" | "Medium" | "Low",
    "matchedSkills": [string],
    "missingSkills": [string],
    "summary": string,
    "recommendation": string
    }}

    Consider:
    - Skill and experience relevance
    - Domain fit
    - Project alignment
    - Communication clarity (in summary)
    - Seniority or role match

    RESUME:
    {json.dumps(parsed_resume, indent=2)}

    JOB DESCRIPTION:
    {json.dumps(job_desc, indent=2)}

    Return **only** valid JSON.
    """

def analyze_resume_with_gemini(parsed_resume: dict, job_desc: dict) -> dict:
    prompt = build_analysis_prompt(parsed_resume, job_desc)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config={"response_mime_type": "application/json"}
        )

        result = json.loads(response.text)
        return result

    except Exception as e:
        print("❌ Error analyzing resume:", e)
        return {"error": str(e)}