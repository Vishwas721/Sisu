import logging
import re
from typing import Dict, Any, Optional
import aiohttp
from config import config

logger = logging.getLogger("leads_pipeline.ai_drafter")

def get_prompt_for_strategy(strategy: str, lead_info: Dict[str, Any], site_summary: str = "") -> str:
    """
    Generate cold email outreach prompt for the LLM using the casual 4-sentence template.
    """
    business_name = lead_info.get("business_name", "your business")

    prompt = f"""
You are an expert cold email copywriter. Write a highly casual, short, 4-sentence email to {business_name}. 

CRITICAL RULES:
1. Speak at a 5th-grade reading level. Use short, simple words.
2. DO NOT use formal corporate speak (e.g., "excellence", "reputation", "innovative").
3. You must follow the exact structure of the template below. 

Use this exact template, but adapt the [bracketed] parts to fit their business:

Template:
Hi,
I came across [Business Name] and noticed there’s an opportunity to [insert the specific fix: e.g., give the website a much more modern look / set up a proper website / streamline your booking process].
I build custom solutions for businesses like yours, with a focus on making them look credible, work better on mobile, and turn more visitors into customers.
If you’re open to seeing what I could do, just reply “interested” and I’ll send you a quick concept.
If not, no worries — you can ignore this email.

Best,
Vishwas
"""
    return prompt

class AIDraftingEngine:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    def _clean_response(self, text: str) -> str:
        """Strip conversational preamble and outer quotes while preserving template structure."""
        text = text.strip()
        prefixes = [
            r"^(here is|here's)\s+(a|the|your)?\s*(outreach|message|cold outreach|email).*?:\s*",
            r"^(subject|re):.*?\n+",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1].strip()

        return text

    async def generate_outreach_message(
        self,
        lead_info: Dict[str, Any],
        site_summary: str = "",
        strategy: Optional[str] = None
    ) -> str:
        """
        Generate casual 4-sentence cold outreach email via Ollama.
        """
        campaign_strategy = strategy or lead_info.get("campaign_strategy") or "legacy_redesign"
        prompt = get_prompt_for_strategy(campaign_strategy, lead_info, site_summary)

        business_name = lead_info.get("business_name", "your business")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.5,
                "top_p": 0.9,
                "num_predict": 250
            }
        }

        endpoint = f"{self.base_url}/api/generate"
        logger.info(f"Generating AI outreach draft for '{business_name}' via Ollama ({self.model})...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_output = data.get("response", "").strip()
                        cleaned = self._clean_response(raw_output)
                        logger.info(f"Successfully generated outreach message for '{business_name}'.")
                        return cleaned
                    else:
                        error_text = await resp.text()
                        logger.error(f"Ollama API returned HTTP {resp.status}: {error_text}")
                        return self._fallback_message(campaign_strategy, business_name)
        except Exception as e:
            logger.error(f"Failed to communicate with Ollama at {endpoint}: {e}")
            return self._fallback_message(campaign_strategy, business_name)

    def _fallback_message(self, strategy: str, business_name: str) -> str:
        """Template-aligned deterministic fallback if Ollama is unreachable."""
        if strategy == "no_website":
            fix = "set up a proper website"
        elif strategy == "ai_automation":
            fix = "streamline your booking process"
        else:
            fix = "give the website a much more modern look"

        return (
            f"Hi,\n"
            f"I came across {business_name} and noticed there’s an opportunity to {fix}.\n"
            f"I build custom solutions for businesses like yours, with a focus on making them look credible, work better on mobile, and turn more visitors into customers.\n"
            f"If you’re open to seeing what I could do, just reply “interested” and I’ll send you a quick concept.\n"
            f"If not, no worries — you can ignore this email.\n\n"
            f"Best,\n"
            f"Vishwas"
        )

if __name__ == "__main__":
    import asyncio
    engine = AIDraftingEngine()
    test_lead = {"business_name": "Apex Dental", "campaign_strategy": "legacy_redesign"}
    print("--- PROMPT ---")
    print(get_prompt_for_strategy("legacy_redesign", test_lead))
    print("\n--- FALLBACK MESSAGE ---")
    print(engine._fallback_message("legacy_redesign", "Apex Dental"))
