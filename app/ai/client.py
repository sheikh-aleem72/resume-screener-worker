import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=API_KEY)


def call_llm(prompt: str) -> str:
    """
    Minimal, guaranteed-working Gemini call.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",   # ✅ NO extra quotes
        contents=prompt,
    )

    if isinstance(response, str):
        text = response

    # Case 2: Proper SDK response object
    elif hasattr(response, "candidates"):
        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = response.candidates[0].content.parts
        if not parts:
            raise RuntimeError("Gemini returned empty content parts")

        text = "".join(part.text for part in parts if hasattr(part, "text") and part.text)

    else:
        raise RuntimeError("Unexpected Gemini response type")

    text = text.strip()
    if not text:
        raise RuntimeError("Gemini returned empty text")

    if text.startswith("```"):
        lines = text.splitlines()
        # remove first and last fence
        text = "\n".join(lines[1:-1]).strip()

    return text
