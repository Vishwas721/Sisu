import re
import time
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import Stealth
from config import config

logger = logging.getLogger("leads_pipeline.extractor")

# Email regex
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

# Common image/asset extensions and dummy domains to ignore
IGNORE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.tiff', '.ico', '.js', '.css', '.woff', '.woff2'}
# A footer this many years behind the current year counts as neglected
STALE_COPYRIGHT_YEARS = 3

# How much each problem makes a business worth pitching. Leads below MIN_LEAD_SCORE are dropped.
ISSUE_WEIGHTS = {
    "site_errors": 45,
    "no_viewport": 35,
    "http": 30,
    "old_copyright": 25,
    "no_booking": 20,
    "manual_form": 15,
    "slow_load": 10,
    "no_meta_description": 5,
    "low_text": 5,
    "no_og": 2,
}
MIN_LEAD_SCORE = 20
PHP_ERROR_PATTERN = re.compile(
    r"<b>(?:Notice|Warning|Deprecated|Fatal error|Parse error)</b>:|There has been a critical error on this website",
    re.IGNORECASE
)
# Businesses with no website at all are the easiest pitch
NO_WEBSITE_SCORE = 50

# Placeholder and tracking domains that show up in page source but are never a business inbox.
# Matched against the email's domain (and its parent domains), never as a substring of the whole address.
IGNORE_DOMAINS = {
    'sentry.io', 'sentry-next.wixpress.com', 'wixpress.com', 'example.com', 'domain.com', 'email.com',
    'yourdomain.com', 'yoursite.com', 'company.com', 'mysite.com', 'website.com', 'test.com',
    'godaddy.com', 'squarespace.com', 'wix.com', 'sentry.wixpress.com',
}
IGNORE_LOCAL_PARTS = {'your', 'yourname', 'name', 'email', 'user', 'username', 'john', 'johndoe', 'jane', 'example'}

def decode_cfemail(encoded: str) -> Optional[str]:
    """Decode a Cloudflare email-protection hex string (first byte is the XOR key)."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except (ValueError, IndexError):
        return None

class WebExtractor:
    SCHEDULING_SIGNATURES = [
        "calendly.com", "acuityscheduling.com", "zocdoc.com", "nexhealth.com",
        "squareup.com/appointments", "setmore.com", "simplybook", "appointlet",
        "jane.app", "vagaro.com", "mindbodyonline.com", "hubspot.com/meetings",
        "tidycal.com", "schedulista.com", "doctolib",
        # Dental / medical
        "localmed.com", "flexbook", "solutionreach", "lighthouse360", "weave.com", "modento",
        "dentrix", "patientpop", "zocdoc", "healthgrades.com/book", "chirotouch", "janeapp.com",
        # Home services
        "servicetitan", "housecallpro", "getjobber.com", "jobber.com", "workiz", "fieldedge",
        "scheduleengine", "servicefusion",
        # Salon / spa / fitness / restaurants
        "booksy.com", "fresha.com", "glossgenius", "styleseat", "schedulicity", "boulevard.io",
        "zenoti", "mindbody", "opentable.com", "resy.com", "sevenrooms", "exploretock",
        # Generic booking embeds
        "booking.setmore", "youcanbook.me", "10to8", "oncehub", "cal.com", "square.site",
        "book.squareup.com", "wixbookings", "bookings-widget",
    ]

    def __init__(self, headless: Optional[bool] = None, timeout_ms: Optional[int] = None):
        self.headless = config.PLAYWRIGHT_HEADLESS if headless is None else headless
        self.timeout_ms = config.PAGE_TIMEOUT_MS if timeout_ms is None else timeout_ms
        self.stealth = Stealth()
        self._playwright_cm = None
        self._browser: Optional[Browser] = None

    async def _get_browser(self) -> Browser:
        """Launch Chromium once and share it; each lead gets its own isolated context."""
        if self._browser is None:
            self._playwright_cm = self.stealth.use_async(async_playwright())
            playwright = await self._playwright_cm.__aenter__()
            self._browser = await playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
        return self._browser

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright_cm is not None:
            await self._playwright_cm.__aexit__(None, None, None)
            self._playwright_cm = None

    async def _wait_for_render(self, page: Page, timeout_ms: int = 8000) -> None:
        """Give JS-rendered sites (Wix, Squarespace, React) time to populate the DOM."""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            # Sites with long-polling or chat widgets never go idle; use what has rendered so far
            pass

    def _clean_email(self, email_str: str) -> Optional[str]:
        email_str = urllib.parse.unquote(email_str).strip().lower().strip(".")
        if any(email_str.endswith(ext) for ext in IGNORE_EXTENSIONS):
            return None
        parts = email_str.split('@')
        if len(parts) != 2:
            return None
        local, domain = parts
        if len(local) < 2 or local in IGNORE_LOCAL_PARTS:
            return None
        # Retina asset names like "logo@2x.png" and npm specifiers like "core-js@3.2.1"
        tld = domain.rsplit(".", 1)[-1]
        if "." not in domain or not tld.isalpha() or len(tld) < 2:
            return None
        labels = domain.split(".")
        if any(".".join(labels[i:]) in IGNORE_DOMAINS for i in range(len(labels) - 1)):
            return None
        return email_str

    def _clean_social_url(self, url: str, platform: str) -> Optional[str]:
        if not url:
            return None
        url = url.strip()
        parsed = urllib.parse.urlparse(url)
        if platform not in parsed.netloc.lower():
            return None
        path = parsed.path.strip("/")
        if not path or path in ("share", "sharer", "home", "intent", "login", "signup", "p"):
            return None
        if "share" in parsed.query.lower():
            return None
        return f"https://{parsed.netloc}/{path}"

    def evaluate_strategy(self, html: str, url: str) -> Dict[str, Any]:
        """
        Score how much this business would benefit from web work and pick a pitch:
        - legacy_redesign: http://, no mobile viewport, or a stale copyright footer.
        - ai_automation: modern site, but no online booking (manual form or nothing at all).
        Returns strategy, human-readable flaws, numeric score and machine-readable issue codes.
        A modern site that already has online booking scores low and is filtered out later.
        """
        soup = BeautifulSoup(html, "html.parser")
        flaws: List[str] = []
        issues: List[str] = []
        score = 0

        # ======================================================================
        # Condition A: legacy_redesign
        # ======================================================================
        # PHP/WordPress errors printed into the page are visible to every visitor
        if PHP_ERROR_PATTERN.search(html):
            flaws.append("Website displays PHP / WordPress error messages to visitors")
            issues.append("site_errors")
            score += ISSUE_WEIGHTS["site_errors"]

        is_http = url.lower().startswith("http://")
        if is_http:
            flaws.append("Insecure HTTP protocol / missing SSL certificate")
            issues.append("http")
            score += ISSUE_WEIGHTS["http"]

        viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
        has_viewport = viewport is not None
        if not has_viewport:
            flaws.append("Missing mobile responsive viewport tag (<meta name='viewport'>)")
            issues.append("no_viewport")
            score += ISSUE_WEIGHTS["no_viewport"]

        # Copyright year extraction
        copyright_pattern = re.compile(
            r'(?:©|&copy;|\(c\)|copyright)\s*(?:[12][0-9]{3}\s*[-–—/]\s*)?([12][0-9]{3})',
            re.IGNORECASE
        )
        current_year = datetime.now().year
        years = [int(y) for y in copyright_pattern.findall(soup.get_text()) if 1990 <= int(y) <= current_year]
        # Judge by the newest year on the page; a single stale mention elsewhere shouldn't count
        newest_year = max(years) if years else None
        has_old_copyright = newest_year is not None and newest_year <= current_year - STALE_COPYRIGHT_YEARS

        if has_old_copyright:
            flaws.append(f"Outdated copyright year ({newest_year}) indicates neglected website maintenance")
            issues.append(f"old_copyright:{newest_year}")
            score += ISSUE_WEIGHTS["old_copyright"]

        if "site_errors" in issues or is_http or not has_viewport or has_old_copyright:
            logger.info(f"[STRATEGY EVAL] Assigned 'legacy_redesign' for {url} (HTTP: {is_http}, No Viewport: {not has_viewport}, Old Copyright: {has_old_copyright})")
            return {"strategy": "legacy_redesign", "flaws": flaws, "score": score, "issues": issues}

        # ======================================================================
        # Condition B: ai_automation
        # ======================================================================
        html_lower = html.lower()
        has_scheduling_widget = any(sig in html_lower for sig in self.SCHEDULING_SIGNATURES)

        if has_scheduling_widget:
            # Modern site that already takes bookings online: little to sell them
            logger.info(f"[STRATEGY EVAL] {url} is modern and already has online booking")
            return {"strategy": "ai_automation", "flaws": flaws, "score": score, "issues": issues}

        # Detect standard manual form elements
        has_manual_form = False
        for form in soup.find_all("form"):
            if form.get("role") == "search":
                continue
            inputs = form.find_all(["input", "textarea"])
            input_types = [inp.get("type", "text").lower() for inp in inputs if inp.name == "input"]
            input_names = [inp.get("name", "").lower() for inp in inputs]

            # Skip pure single search inputs
            if any(name in ("q", "s", "search", "query") for name in input_names) and len(inputs) <= 2:
                continue

            has_contact_fields = any(t in ("text", "email", "tel") for t in input_types) or form.find("textarea") is not None
            if has_contact_fields:
                has_manual_form = True
                break

        if has_manual_form:
            flaws.append("Manual contact forms cause lead drop-off / lacks 24/7 automated scheduling widget")
            issues.append("manual_form")
            score += ISSUE_WEIGHTS["manual_form"]
        else:
            flaws.append("No way to book or request an appointment online")
            issues.append("no_booking")
            score += ISSUE_WEIGHTS["no_booking"]

        logger.info(f"[STRATEGY EVAL] Assigned 'ai_automation' for {url} (manual form: {has_manual_form})")
        return {"strategy": "ai_automation", "flaws": flaws, "score": score, "issues": issues}

    async def _extract_from_page(self, page: Page, base_url: str) -> Dict[str, Any]:
        """Extract emails, socials, and technical details from page DOM."""
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Emails
        emails: Set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                clean = href.split("mailto:")[1].split("?")[0].strip()
                cleaned = self._clean_email(clean)
                if cleaned:
                    emails.add(cleaned)

        text_matches = EMAIL_REGEX.findall(html_content)
        for m in text_matches:
            cleaned = self._clean_email(m)
            if cleaned:
                emails.add(cleaned)

        # Cloudflare hides emails as hex in data-cfemail or /cdn-cgi/l/email-protection#<hex>
        cf_encoded = [el["data-cfemail"] for el in soup.find_all(attrs={"data-cfemail": True})]
        cf_encoded += [
            a["href"].split("#", 1)[1] for a in soup.find_all("a", href=True)
            if "/cdn-cgi/l/email-protection#" in a["href"]
        ]
        for encoded in cf_encoded:
            decoded = decode_cfemail(encoded)
            cleaned = self._clean_email(decoded) if decoded else None
            if cleaned:
                emails.add(cleaned)

        # 2. Instagram & LinkedIn
        instagram_url = None
        linkedin_url = None

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "instagram.com" in href and not instagram_url:
                cleaned = self._clean_social_url(href, "instagram.com")
                if cleaned:
                    instagram_url = cleaned
            elif "linkedin.com" in href and not linkedin_url:
                cleaned = self._clean_social_url(href, "linkedin.com")
                if cleaned:
                    linkedin_url = cleaned

        # 3. Technical metadata & content
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        meta_desc_el = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        meta_desc = meta_desc_el["content"].strip() if meta_desc_el and meta_desc_el.get("content") else ""

        og_title = soup.find("meta", attrs={"property": "og:title"})
        has_og = og_title is not None

        headings = [h.get_text().strip() for h in soup.find_all(["h1", "h2"]) if h.get_text().strip()]
        heading_text = " | ".join(headings[:3])

        for script in soup(["script", "style", "svg", "noscript"]):
            script.decompose()
        body_text = " ".join(soup.stripped_strings)[:800]

        # General technical checks
        general_flaws = []
        general_issues = []
        if not meta_desc:
            general_flaws.append("Missing search engine meta description")
            general_issues.append("no_meta_description")
        if not has_og:
            general_flaws.append("Missing OpenGraph social preview tags")
            general_issues.append("no_og")
        if len(body_text) < 150:
            general_flaws.append("Low text content / potential rendering or SEO indexation problem")
            general_issues.append("low_text")

        # 4. Strategy Evaluation
        evaluation = self.evaluate_strategy(html_content, page.url or base_url)
        score = evaluation["score"] + sum(ISSUE_WEIGHTS[i] for i in general_issues)

        return {
            "emails": sorted(emails),
            "instagram_url": instagram_url,
            "linkedin_url": linkedin_url,
            "title": title,
            "meta_description": meta_desc,
            "headings": heading_text,
            "text_summary": body_text,
            "technical_flaws": evaluation["flaws"] + general_flaws,
            "issues": evaluation["issues"] + general_issues,
            "lead_score": score,
            "campaign_strategy": evaluation["strategy"],
            "html_length": len(html_content)
        }

    async def scrape_lead(
        self,
        target_url: str,
        business_name: str = "",
        campaign_strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch Playwright with stealth evasions, visit URL, and evaluate DOM.
        If campaign_strategy == 'no_website', skips Playwright scraping entirely.
        """
        # Step 3 Optimization: If lead has no website, bypass browser scraping completely
        if campaign_strategy == "no_website":
            logger.info(f"[SCRAPE BYPASS] Skipping Playwright scraping for '{business_name}' (campaign_strategy='no_website').")
            return {
                "website_url": target_url,
                "business_name": business_name,
                "emails": [],
                "instagram_url": target_url if "instagram.com" in target_url else None,
                "linkedin_url": None,
                "raw_summary": f"Business Name: {business_name}. Listed online ({target_url}), but no dedicated website.",
                "technical_flaws": ["No dedicated business website found"],
                "issues": ["no_website"],
                "lead_score": NO_WEBSITE_SCORE,
                "scrape_status": "skipped_no_website",
                "load_time_sec": 0.0,
                "campaign_strategy": "no_website"
            }

        logger.info(f"Scraping lead [{business_name}]: {target_url}")
        result: Dict[str, Any] = {
            "website_url": target_url,
            "business_name": business_name,
            "emails": [],
            "instagram_url": None,
            "linkedin_url": None,
            "raw_summary": "",
            "technical_flaws": [],
            "issues": [],
            "lead_score": 0,
            "scrape_status": "failed",
            "load_time_sec": 0.0,
            "campaign_strategy": "legacy_redesign"
        }

        browser = await self._get_browser()
        # No custom user agent: a hard-coded Chrome version that disagrees with the real browser's
        # client hints gets flagged by bot protection (Cloudflare etc.) and returns 403
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/Chicago"
        )
        page = await context.new_page()

        try:
            # Start timing after browser launch so Chromium startup isn't counted as page load
            start_time = time.time()
            response = await page.goto(target_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            status_code = response.status if response else 0
            load_time = round(time.time() - start_time, 2)
            result["load_time_sec"] = load_time

            if load_time > 5.0:
                result["technical_flaws"].append(f"Slow initial page load time ({load_time}s)")
                result["issues"].append("slow_load")
                result["lead_score"] += ISSUE_WEIGHTS["slow_load"]

            await self._wait_for_render(page)

            # Extract page data and evaluate strategy
            page_data = await self._extract_from_page(page, target_url)
            result["emails"] = page_data["emails"]
            result["instagram_url"] = page_data["instagram_url"]
            result["linkedin_url"] = page_data["linkedin_url"]
            result["technical_flaws"].extend(page_data["technical_flaws"])
            # Lead with the strongest problems: page-level issues first, slow load after
            result["issues"] = page_data["issues"] + result["issues"]
            result["lead_score"] += page_data["lead_score"]
            result["campaign_strategy"] = page_data["campaign_strategy"]
            if result["lead_score"] < MIN_LEAD_SCORE:
                result["campaign_strategy"] = "not_a_lead"

            # If no emails found on homepage, check /contact or /about
            if not result["emails"]:
                contact_link = (
                    await page.query_selector('a[href*="contact" i]')
                    or await page.query_selector('a[href*="about" i]')
                )
                if contact_link:
                    try:
                        contact_href = await contact_link.get_attribute("href")
                        if contact_href:
                            full_contact_url = urllib.parse.urljoin(target_url, contact_href)
                            logger.info(f"Visiting contact page for {business_name}: {full_contact_url}")
                            await page.goto(full_contact_url, wait_until="domcontentloaded", timeout=15000)
                            await self._wait_for_render(page)
                            contact_data = await self._extract_from_page(page, full_contact_url)
                            for em in contact_data["emails"]:
                                if em not in result["emails"]:
                                    result["emails"].append(em)
                            if not result["instagram_url"] and contact_data["instagram_url"]:
                                result["instagram_url"] = contact_data["instagram_url"]
                            if not result["linkedin_url"] and contact_data["linkedin_url"]:
                                result["linkedin_url"] = contact_data["linkedin_url"]
                    except Exception as ce:
                        logger.debug(f"Contact page lookup failed for {target_url}: {ce}")

            summary_parts = [
                f"Business Name: {business_name}",
                f"Website: {target_url}",
                f"Assigned Campaign Strategy: {result['campaign_strategy']} (lead score {result['lead_score']})",
                f"Page Title: {page_data['title']}",
                f"Meta Description: {page_data['meta_description'] or 'None provided'}",
                f"Key Headings: {page_data['headings'] or 'None'}",
                f"Detected Flaws & Opportunities: {', '.join(result['technical_flaws']) if result['technical_flaws'] else 'None'}",
                f"Text Snippet: {page_data['text_summary'][:400]}"
            ]
            result["raw_summary"] = "\n".join(summary_parts)
            result["scrape_status"] = "success" if status_code < 400 else f"http_{status_code}"

        except Exception as e:
            logger.error(f"Error scraping {target_url}: {e}")
            result["scrape_status"] = "error"
            result["campaign_strategy"] = "legacy_redesign"
            result["technical_flaws"].append("Website unresponsive, timed out, or connection failed")
            result["raw_summary"] = f"Failed to load page. Error: {str(e)}"
        finally:
            await context.close()

        return result
