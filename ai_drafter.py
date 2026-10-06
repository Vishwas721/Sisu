import logging
import re
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
from config import config

logger = logging.getLogger("leads_pipeline.ai_drafter")

# ==============================================================================
# Observation -> consequence copy, keyed by the issue codes the extractor emits.
# Each email opens with one concrete thing the owner can verify in ten seconds,
# says why it costs them customers, then makes one low-effort offer.
# ==============================================================================

# How a customer would say "looking for ___" for niches whose key isn't a natural noun
NICHE_NOUNS = {
    "hvac": "an HVAC company", "roofing": "a roofer", "landscaping": "a landscaper",
    "construction": "a builder", "solar": "a solar installer", "cleaning": "a cleaning service",
    "pest control": "a pest control company", "flooring": "a flooring company",
    "remodeling": "a remodeling contractor", "pool service": "a pool service",
    "physiotherapy": "a physiotherapist", "plastic surgery": "a plastic surgeon",
    "veterinary": "a vet", "doctor": "a doctor", "clinic": "a clinic",
    "real estate": "a real estate agent", "architecture": "an architect",
    "insurance": "an insurance agent", "marketing agency": "a marketing agency",
    "property management": "a property manager", "moving company": "a moving company",
    "auto repair": "an auto repair shop", "salon": "a salon", "spa": "a spa", "gym": "a gym",
}

def _niche_phrase(niche: Optional[str]) -> str:
    """'dentist' -> 'a dentist', 'hvac' -> 'an HVAC company'."""
    if not niche:
        return "a local business"
    niche = niche.lower().strip()
    if niche in NICHE_NOUNS:
        return NICHE_NOUNS[niche]
    return f"{'an' if niche[0] in 'aeiou' else 'a'} {niche}"

def _site_label(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or url

def _review_praise(lead: Dict[str, Any]) -> str:
    rating, reviews = lead.get("rating"), lead.get("review_count")
    if rating and reviews and rating >= 4.3 and reviews >= 10:
        return f" ({rating:.1f} stars from {reviews} reviews is really solid)"
    return ""

def _observation(issue: str, lead: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    """(subject, observation sentence, why-it-matters sentence) for one issue code."""
    name = lead.get("business_name") or "your business"
    site = _site_label(lead.get("website_url", ""))
    looking_for = _niche_phrase(lead.get("niche"))
    city = lead.get("city") or "your area"

    if issue == "site_errors":
        return (
            f"error messages on {site}",
            f"When I opened {site}, the page showed a block of WordPress/PHP error messages instead of the normal site.",
            "Visitors see that first, and most will assume the business is closed or not looking after things.",
        )
    if issue == "no_viewport":
        return (
            f"{name}'s site on phones",
            f"I pulled up {site} on my phone and it loads the desktop layout shrunk down, so you have to pinch and zoom to read anything.",
            f"Most people looking for {looking_for} in {city} are searching on their phone, and Google ranks sites that aren't mobile-friendly lower too.",
        )
    if issue == "http":
        return (
            f"\"Not secure\" warning on {site}",
            f"When I opened {site}, Chrome showed a \"Not secure\" warning next to the address because the site doesn't have an SSL certificate.",
            f"That warning makes a lot of people back out before they ever call, especially when they're comparing a few options.",
        )
    if issue.startswith("old_copyright:"):
        year = issue.split(":", 1)[1]
        return (
            f"quick note about {site}",
            f"I noticed the footer on {site} still says © {year}, so it looks like the site hasn't been touched in a while.",
            "People quietly judge whether a business is still active (and how careful it is) from its website.",
        )
    if issue == "slow_load":
        secs = lead.get("load_time_sec")
        took = f"about {secs:.0f} seconds" if secs else "a long time"
        return (
            f"{site} load time",
            f"{site} took {took} to load for me.",
            "Over half of mobile visitors leave if a page takes more than 3 seconds, and they usually end up on a competitor's site.",
        )
    if issue == "no_booking":
        return (
            f"online booking for {name}",
            f"I couldn't find a way to book or request an appointment on {site}; the only option is to call.",
            f"Lots of people look for {looking_for} in the evening or on a lunch break and just book with whoever lets them do it online.",
        )
    if issue == "manual_form":
        return (
            f"online booking for {name}",
            f"The contact form on {site} lets people send a message, but there's no way to actually pick a time and book.",
            "Every back-and-forth to find a slot is a chance for them to book somewhere else instead.",
        )
    if issue == "no_website":
        return (
            f"website for {name}?",
            f"I was looking for {looking_for} in {city} and found {name} online{_review_praise(lead)}, but couldn't find a website for you.",
            "Without one, a lot of people who hear about you and search your name end up on a competitor's site instead.",
        )
    return None

OFFERS = {
    "legacy_redesign": "I'd be happy to put together a free mockup of what a modern version of your homepage could look like. No strings attached. Want me to send it over?",
    "ai_automation": "I can set up online booking that drops appointments straight into your calendar. Want me to send a quick 2-minute video showing how it would look on your site?",
    "no_website": "I build simple, fast websites for local businesses. I could put together a free one-page preview for {name} so you can see it before deciding anything. Want me to send it?",
}

# Order in which issues make the strongest opener
ISSUE_PRIORITY = ["no_website", "site_errors", "no_viewport", "http", "old_copyright", "no_booking", "manual_form", "slow_load"]

def _pick_issue(issues: List[str], strategy: str) -> str:
    for wanted in ISSUE_PRIORITY:
        for issue in issues:
            if issue == wanted or issue.startswith(wanted + ":"):
                return issue
    return {"no_website": "no_website", "ai_automation": "no_booking"}.get(strategy, "no_viewport")

def _signature() -> str:
    lines = ["", "Best,", config.SENDER_NAME, "", "--"]
    if config.SENDER_ADDRESS:
        # CAN-SPAM requires a physical postal address in commercial email
        lines.append(config.SENDER_ADDRESS)
    lines.append("Not interested? Just reply \"no thanks\" and I won't email again.")
    return "\n".join(lines)

def build_email(lead: Dict[str, Any], strategy: str) -> Tuple[str, str]:
    """Deterministic personalized (subject, body) from the issues found on the lead's site."""
    issue = _pick_issue(lead.get("issues", []), strategy)
    subject, observation, consequence = _observation(issue, lead) or _observation("no_viewport", lead)
    offer_key = strategy if strategy in OFFERS else "legacy_redesign"
    offer = OFFERS[offer_key].format(name=lead.get("business_name") or "you")
    body = f"Hi,\n\n{observation} {consequence}\n\n{offer}\n{_signature()}"
    return subject, body

def get_prompt_for_strategy(strategy: str, lead_info: Dict[str, Any], site_summary: str = "") -> str:
    """Prompt asking the LLM to reword the deterministic draft without losing its specifics."""
    _, draft = build_email(lead_info, strategy)
    body = draft.split("\nBest,")[0].strip()
    return f"""Rewrite this cold email so it sounds like a real person typed it quickly. Keep it under 90 words.

RULES:
- Keep the specific observation about their website exactly as true as it is now. Do not invent new facts.
- Keep the offer and the question at the end.
- You are an outside web developer writing TO the business. Never write as if you are the business.
- No subject line, no sign-off, no placeholders, no brackets. Output only the email body starting with "Hi,".

EMAIL:
{body}
"""

class AIDraftingEngine:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, use_llm: Optional[bool] = None):
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self.use_llm = config.USE_LLM_DRAFTS if use_llm is None else use_llm

    def _clean_response(self, text: str) -> str:
        """Strip conversational preamble and outer quotes."""
        text = text.strip()
        prefixes = [
            r"^(here is|here's)\s+(a|the|your)?\s*(rewritten|revised)?\s*(outreach|message|cold outreach|email).*?:\s*",
            r"^(subject|re):.*?\n+",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1].strip()

        return text

    def _llm_output_ok(self, text: str, lead_info: Dict[str, Any]) -> bool:
        """Small local models drift; only accept output that kept the shape of the draft."""
        if not text.lower().startswith("hi") or "[" in text or "{" in text:
            return False
        if len(text.split()) > 130:
            return False
        if re.search(r"\b(our (practice|clinic|team|services)|we provide)\b", text, re.IGNORECASE):
            return False
        return True

    async def _reword_with_llm(self, lead_info: Dict[str, Any], strategy: str) -> Optional[str]:
        payload = {
            "model": self.model,
            "prompt": get_prompt_for_strategy(strategy, lead_info),
            "stream": False,
            "options": {"temperature": 0.6, "top_p": 0.9, "num_predict": 220},
        }
        endpoint = f"{self.base_url}/api/generate"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status != 200:
                        logger.error(f"Ollama API returned HTTP {resp.status}: {await resp.text()}")
                        return None
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Failed to communicate with Ollama at {endpoint}: {e}")
            return None

        text = self._clean_response(data.get("response", ""))
        if not self._llm_output_ok(text, lead_info):
            logger.warning(f"Discarding off-template LLM draft for '{lead_info.get('business_name')}'")
            return None
        return text

    async def generate_outreach_message(
        self,
        lead_info: Dict[str, Any],
        site_summary: str = "",
        strategy: Optional[str] = None
    ) -> str:
        """
        Return "Subject: ...\\n\\n<body>" personalized to the lead's most important website issue.
        With USE_LLM_DRAFTS the body is reworded by Ollama, falling back to the template if the
        model's output doesn't pass validation.
        """
        campaign_strategy = strategy or lead_info.get("campaign_strategy") or "legacy_redesign"
        subject, body = build_email(lead_info, campaign_strategy)

        if self.use_llm:
            reworded = await self._reword_with_llm(lead_info, campaign_strategy)
            if reworded:
                body = f"{reworded}\n{_signature()}"

        logger.info(f"Drafted outreach for '{lead_info.get('business_name')}' (strategy: {campaign_strategy}).")
        return f"Subject: {subject}\n\n{body}"

if __name__ == "__main__":
    import asyncio
    engine = AIDraftingEngine(use_llm=False)
    samples = [
        ({"business_name": "Apex Dental", "niche": "dentist", "city": "Austin", "website_url": "http://www.apexdental.com",
          "issues": ["http", "no_viewport", "old_copyright:2017"]}, "legacy_redesign"),
        ({"business_name": "Bright Smiles", "niche": "dentist", "city": "Austin", "website_url": "https://brightsmiles.com",
          "issues": ["manual_form"]}, "ai_automation"),
        ({"business_name": "Bob's Plumbing", "niche": "plumber", "city": "Austin", "website_url": "https://maps.google.com/?cid=1",
          "issues": ["no_website"], "rating": 4.8, "review_count": 112}, "no_website"),
    ]
    for lead, strat in samples:
        print(asyncio.run(engine.generate_outreach_message(lead, strategy=strat)))
        print("=" * 70)
