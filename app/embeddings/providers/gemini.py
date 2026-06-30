import os
from dotenv import load_dotenv
from google import genai
from app.embeddings.providers.base import EmbeddingProvider

load_dotenv()

class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Gemini Embedding Provider
    Phase 4.2 compliant
    """

    model_name = "models/embedding-001"

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        print(f"Gemin API key: {api_key}")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty text")

        try:
            result = genai.embed_content(
                model=self.model_name,
                content=text,
                task_type="semantic_similarity"
            )

            embedding = result.get("embedding")
            if not embedding:
                raise RuntimeError("Gemini returned empty embedding")

            return embedding

        except Exception as e:
            # IMPORTANT: bubble up error for worker retry
            raise RuntimeError(f"Gemini embedding failed: {str(e)}") from e
