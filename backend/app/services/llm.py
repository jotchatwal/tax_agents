import logging
import requests
from typing import Optional, Dict, Any
from backend.app.config import settings

logger = logging.getLogger(__name__)

class GeminiLLMService:
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL or "gemini-3.5-flash-lite"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """
        Call Gemini REST API for guided natural language synthesis.
        Strict Invariant: LLM is never permitted to perform tax arithmetic or invent rates.
        """
        if not self.api_key:
            logger.info("No LLM API key configured; using deterministic synthesis.")
            return None

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=12
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            else:
                logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Gemini API call timed out or failed ({e}); falling back to deterministic explanation.")

        return None

llm_service = GeminiLLMService()
