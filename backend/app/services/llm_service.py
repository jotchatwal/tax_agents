import os
import json
import logging
from typing import Dict, Any, List, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.api_key = settings.LLM_API_KEY or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
        self.model_name = settings.LLM_MODEL or "gemini-2.5-flash"
        self._client = None

    def _get_gemini_client(self):
        if self._client is None and self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Google GenAI Client: {e}")
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key and self._get_gemini_client())

    def extract_intent_and_entities(
        self,
        user_message: str,
        current_salary: Optional[float] = None,
        profile_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to dynamically classify intent and extract financial entities from user input.
        Returns None if LLM is unavailable or fails.
        """
        client = self._get_gemini_client()
        if not client:
            return None

        baseline_str = f"Current Confirmed Annual Salary: ${current_salary:,.2f} CAD" if current_salary else "Current Confirmed Annual Salary: Unknown"

        prompt = f"""You are a financial NLP parser for TaxPilot AI (Canadian personal tax system).
{baseline_str}

Analyze the user's input and return ONLY a valid JSON object matching this schema:
{{
  "intent": "greeting" | "profile_update" | "scenario" | "memory_governance" | "onboarding" | "question",
  "is_factual_update": boolean,
  "salary_cad": number or null,
  "salary_increment_cad": number or null,
  "calculated_new_salary_cad": number or null,
  "effective_date": string or null,
  "rrsp_contribution_cad": number or null,
  "rrsp_limit_cad": number or null,
  "tuition_amount_cad": number or null,
  "life_event": string or null,
  "memory_action": "delete" | "correct" | null,
  "confidence": number between 0.0 and 1.0,
  "reasoning": string
}}

GUIDELINES:
1. "is_factual_update": Set to true whenever the user reports an actual factual life change (e.g. "I got a promotion", "I got a raise", "my salary is now X", "I changed jobs", "my RRSP limit is X"), EVEN IF they also ask what to look forward to or ask a question in the same sentence. If is_factual_update is true, the primary intent should be "profile_update".
2. If the user reports an increment or raise (e.g. "increment of 20k", "got a $15,000 raise"):
   - Put 20000 into "salary_increment_cad".
   - If current salary is known (e.g. 95000), calculate "calculated_new_salary_cad" = 95000 + 20000 = 115000.
3. If user states an absolute new salary (e.g. "my salary is now 105,000 CAD", "income increased to 202,000"), put that number into "salary_cad" and "calculated_new_salary_cad".
4. If user mentions an RRSP contribution or deduction (e.g. "deduction of $7,000", "contribute 7k to RRSP"), put that amount into "rrsp_contribution_cad".
5. If user mentions their official CRA RRSP limit or Notice of Assessment limit (e.g. "my RRSP deduction limit is $32,490"), put that amount into "rrsp_limit_cad".
6. If user states when the change takes effect (e.g. "effective June 1st", "starting next month", "as of May 2025"), provide the date in "YYYY-MM-DD" format in "effective_date". Otherwise leave null.

User Input: "{user_message}"
"""
        models_to_try = [self.model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                )
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text.rsplit("```", 1)[0]
                    text = text.strip()
                return json.loads(text)
            except Exception as e:
                logger.warning(f"LLM intent extraction failed with {m}: {e}")
        return None

    def generate_grounded_response(
        self,
        user_message: str,
        profile: Dict[str, Any],
        memories: List[Dict[str, Any]],
        calculations: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        tax_rules: List[Dict[str, Any]],
        proposed_changes: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Use LLM to generate an intelligent, personalized conversational tax response.
        Enforces STRICT GROUNDING on the deterministic calculation results.
        Returns None if LLM is unavailable or fails.
        """
        client = self._get_gemini_client()
        if not client:
            return None

        calcs_summary = json.dumps(calculations, indent=2, default=str)
        recs_summary = json.dumps(recommendations, indent=2, default=str)
        memories_summary = json.dumps(
            [{"type": m.get("memory_type"), "content": m.get("content"), "status": m.get("governance", {}).get("status")} for m in memories],
            indent=2
        )
        rules_summary = json.dumps(
            [{"rule_id": r.get("rule_id"), "name": r.get("rule_name"), "url": r.get("source_url")} for r in tax_rules],
            indent=2
        )

        prompt = f"""You are TaxPilot AI, an elite, user-governed Canadian tax-planning companion specializing in Ontario tax year 2025.
The user is speaking with you in a chat interface.

CRITICAL ARCHITECTURAL RULES & INVARIANTS:
1. ZERO ARITHMETIC: NEVER calculate or invent numbers yourself. You MUST use ONLY the exact numbers provided in the DETERMINISTIC ENGINE CALCULATIONS below.
2. CITATIONS: Include official links from the VERIFIED TAX RULES (e.g. CRA RRSP guidelines, Ontario Ministry of Finance brackets).
3. GOVERNED MEMORY: Explicitly refer to the user's confirmed facts from their MongoDB Atlas memories. If there was an update/circumstance change (such as a new salary superseding an old memory), explicitly acknowledge the prior memory being archived as superseded and how the new higher marginal rate increases their tax savings.
4. TONE: Professional, encouraging, clear, formatted in clean Markdown with headers and bullet points.

USER MESSAGE:
"{user_message}"

USER TAX PROFILE & PROPOSED CHANGES:
Income: ${calculations.get('current_income', 0):,.2f} CAD
Proposed Changes: {json.dumps(proposed_changes, default=str)}

VERIFIED ATLAS MEMORIES:
{memories_summary}

DETERMINISTIC ENGINE CALCULATIONS (USE EXACT NUMBERS):
{calcs_summary}

RECOMMENDATIONS:
{recs_summary}

VERIFIED OFFICIAL TAX RULES:
{rules_summary}

Write the response now in Markdown:"""

        models_to_try = [self.model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"LLM response generation failed with {m}: {e}")
        return None

llm_service = LLMService()
