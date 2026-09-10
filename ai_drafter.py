import logging
import re
from typing import Dict, Any, Optional
import aiohttp
from config import config

logger = logging.getLogger("leads_pipeline.ai_drafter")

# Verbatim negative constraint required across all strategy prompts
CRITICAL_NEGATIVE_CONSTRAINT = (
    "YOU ARE NOT THE BUSINESS. NEVER pretend to be the dentist/company. "
    "NEVER use first-person pronouns like 'Our practice' or 'We provide' when referring to their services. "
    "You are an external tech consultant writing an email TO them."
)

def get_prompt_for_strategy(strategy: str, lead_info: Dict[str, Any], site_summary: str) -> str:
    """
    Router function selecting one of three distinct, hardened prompts based on campaign_strategy:
    - no_website: Pitches dedicated booking page to capture lost Google search traffic.
    - legacy_redesign: References specific technical neglect (outdated copyright, mobile layout).
    - ai_automation: Compliments modern site, points out manual form friction, pitches 24/7 AI booking.
    """
    business_name = lead_info.get("business_name", "your business")
    niche = lead_info.get("niche", "local business")
    city = lead_info.get("city", "your area")
    website_url = lead_info.get("website_url", "")
    flaws = lead_info.get("technical_flaws", [])
    flaws_text = ", ".join(flaws) if flaws else "unoptimized mobile layout and slow asset loading"

    social_channel = lead_info.get("instagram_url") or lead_info.get("facebook_url") or "Instagram/Facebook"

    if strategy == "no_website":
        return f"""You are an external tech and web development consultant writing a cold email to the owner of {business_name} in {city}.

CRITICAL NEGATIVE CONSTRAINTS:
{CRITICAL_NEGATIVE_CONSTRAINT}

Context:
- Business: {business_name} ({niche})
- Location: {city}
- Status: The business has an active social media presence ({social_channel}), but NO dedicated business website or online booking page.

Instructions:
Write a strict 3-sentence personalized cold outreach email:
Sentence 1: Compliment their active social media presence and community engagement.
Sentence 2: Explain that without a dedicated website, they are losing high-intent local clients who search directly on Google.
Sentence 3: Pitch the development of a dedicated online booking and credibility page to capture lost Google search traffic.

Strict Rules:
- Exactly 3 sentences.
- Professional, concise, consultative tone.
- Do NOT include subject lines, preamble, placeholders, or quotes. Output ONLY the 3 sentences."""

    elif strategy == "ai_automation":
        return f"""You are an external AI and automation consultant writing a cold email to the owner of {business_name} in {city}.

CRITICAL NEGATIVE CONSTRAINTS:
{CRITICAL_NEGATIVE_CONSTRAINT}

Context:
- Business: {business_name} ({niche})
- Location: {city}
- Website: {website_url}
- Site Summary: {site_summary[:400] if site_summary else 'Modern business website'}
- Observation: The website is modern and professional, but relies on static manual contact forms for lead capture rather than an automated scheduling integration.

Instructions:
Write a strict 3-sentence personalized cold outreach email:
Sentence 1: Compliment their modern, professional website and online presentation.
Sentence 2: Point out that static manual contact forms cause friction and delayed response times, causing potential clients to look elsewhere.
Sentence 3: Pitch a lightweight AI receptionist and automated scheduling integration to book clients 24/7 without manual staff overhead.

Strict Rules:
- Exactly 3 sentences.
- Professional, concise, consultative tone.
- Do NOT include subject lines, preamble, placeholders, or quotes. Output ONLY the 3 sentences."""

    else:
        # Default strategy: legacy_redesign
        return f"""You are an external tech and web development consultant writing a cold email to the owner of {business_name} in {city}.

CRITICAL NEGATIVE CONSTRAINTS:
{CRITICAL_NEGATIVE_CONSTRAINT}

Context:
- Business: {business_name} ({niche})
- Location: {city}
- Website: {website_url}
- Specific technical neglect identified: {flaws_text}
- Site Summary: {site_summary[:400] if site_summary else 'Local business website'}

Instructions:
Write a strict 3-sentence personalized cold outreach email:
Sentence 1: Compliment their business and reputation in {city}.
Sentence 2: Reference the specific technical neglect found on their website ({flaws_text}) and explain how it damages mobile user experience and search ranking.
Sentence 3: Pitch a modern website redesign to turn visitors into confirmed clients.

Strict Rules:
- Exactly 3 sentences.
- Professional, concise, consultative tone.
- Do NOT include subject lines, preamble, placeholders, or quotes. Output ONLY the 3 sentences."""

class AIDraftingEngine:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    def _clean_response(self, text: str) -> str:
        """Strip conversational filler, quotes, and markdown formatting."""
        text = text.strip()
        prefixes = [
            r"^(here is|here's)\s+(a|the|your)?\s*(outreach|message|cold outreach|email).*?:",
            r"^(subject|re):.*?\n+",
            r"^dear.*?\n+",
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
        Route to strategy-specific prompt, send to local Ollama instance,
        and return strict 3-sentence personalized cold email.
        """
        campaign_strategy = strategy or lead_info.get("campaign_strategy") or "legacy_redesign"
        prompt = get_prompt_for_strategy(campaign_strategy, lead_info, site_summary)

        business_name = lead_info.get("business_name", "your business")
        niche = lead_info.get("niche", "local business")
        city = lead_info.get("city", "your area")
        flaws = lead_info.get("technical_flaws", [])
        flaws_text = ", ".join(flaws) if flaws else "unoptimized mobile layout and slow asset loading"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.5,
                "top_p": 0.9,
                "num_predict": 180
            }
        }

        endpoint = f"{self.base_url}/api/generate"
        logger.info(f"Generating AI outreach draft for strategy='{campaign_strategy}' via Ollama ({self.model})...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_output = data.get("response", "").strip()
                        cleaned = self._clean_response(raw_output)
                        logger.info(f"Successfully generated outreach message for strategy '{campaign_strategy}'.")
                        return cleaned
                    else:
                        error_text = await resp.text()
                        logger.error(f"Ollama API returned HTTP {resp.status}: {error_text}")
                        return self._fallback_message(campaign_strategy, business_name, niche, city, flaws_text)
        except Exception as e:
            logger.error(f"Failed to communicate with Ollama at {endpoint}: {e}")
            return self._fallback_message(campaign_strategy, business_name, niche, city, flaws_text)

    def _fallback_message(self, strategy: str, business_name: str, niche: str, city: str, flaws: str) -> str:
        """Strategy-specific deterministic fallback if Ollama is unreachable."""
        if strategy == "no_website":
            return (
                f"I came across {business_name}'s social profile in {city} and was impressed by your strong community presence. "
                f"However, without a dedicated business website, you are likely missing out on patients searching directly on Google. "
                f"Would you be open to a quick 3-minute video showing how a streamlined booking and credibility page could capture that lost search traffic?"
            )
        elif strategy == "ai_automation":
            return (
                f"I visited {business_name}'s website in {city} and was impressed by your clean, modern layout. "
                f"However, relying on manual contact forms often causes delays that lead prospective patients to book elsewhere. "
                f"Would you be open to a quick 3-minute video showing how a 24/7 AI scheduling assistant can automate your bookings directly?"
            )
        else:
            return (
                f"I was reviewing {business_name}'s website in {city} and love the high-quality {niche} services you offer. "
                f"However, I noticed {flaws}, which hurts your search ranking and mobile patient experience. "
                f"Would you be open to a quick 3-minute video showing how a modern redesign can double your online conversions?"
            )
