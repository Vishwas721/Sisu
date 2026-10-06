import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import config, TARGET_CITIES, TARGET_NICHES
from database import Database
from discovery import discover_leads, make_dedupe_key
from extractor import WebExtractor
from ai_drafter import AIDraftingEngine

# ==============================================================================
# Pipeline Configuration & Constants
# ==============================================================================
DAILY_QUOTA = 15
STATE_FILE = Path(__file__).parent / "pipeline_state.json"
LEGACY_STATE_FILE = Path(__file__).parent / "last_city.json"

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("leads_pipeline")

# ==============================================================================
# Nested Rotation Mathematics
# ==============================================================================
def get_next_target(
    current_city_index: int,
    current_niche_index: int,
    total_cities: int,
    total_niches: int
) -> Tuple[int, int]:
    """
    Calculate the next (city_index, niche_index) position in the nested rotation:
    City A -> Niche 1, City A -> Niche 2 ... City A -> Niche N, then City B -> Niche 1.
    """
    next_niche = current_niche_index + 1
    if next_niche < total_niches:
        return current_city_index, next_niche
    else:
        next_city = (current_city_index + 1) % total_cities
        return next_city, 0

# ==============================================================================
# State Persistence (Dual-Rotation Memory Tracking)
# ==============================================================================
def load_state(
    state_file: Path,
    city_names: List[str],
    niche_names: List[str],
    force_next: bool = False
) -> Tuple[int, int, bool]:
    """
    Load dual rotation position (city_index, niche_index, was_exhausted) from the local state file.
    Supports backward compatibility with legacy last_city.json if pipeline_state.json is not present.
    """
    total_cities = len(city_names)
    total_niches = len(niche_names)

    # 1. Check primary pipeline_state.json
    target_path = state_file if state_file.exists() else (LEGACY_STATE_FILE if LEGACY_STATE_FILE.exists() else None)

    if not target_path:
        logger.info(
            f"[STATE] No previous state file found. Starting rotation from "
            f"city 0 ('{city_names[0]}') and niche 0 ('{niche_names[0]}')."
        )
        return 0, 0, False

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        last_city = state_data.get("last_city")
        last_city_idx = state_data.get("last_city_index")
        next_city_idx = state_data.get("next_city_index")

        last_niche = state_data.get("last_niche")
        last_niche_idx = state_data.get("last_niche_index")
        next_niche_idx = state_data.get("next_niche_index")

        was_exhausted = state_data.get("target_exhausted", state_data.get("city_exhausted", False))
        timestamp = state_data.get("updated_at", "unknown")

        # Resolve city index
        if last_city_idx is None and last_city in city_names:
            last_city_idx = city_names.index(last_city)
        if last_city_idx is None or not (0 <= last_city_idx < total_cities):
            last_city_idx = 0

        # Resolve niche index
        if last_niche_idx is None and last_niche in niche_names:
            last_niche_idx = niche_names.index(last_niche)
        if last_niche_idx is None or not (0 <= last_niche_idx < total_niches):
            last_niche_idx = 0

        # Resolve next indices
        if next_city_idx is None or next_niche_idx is None:
            computed_city, computed_niche = get_next_target(last_city_idx, last_niche_idx, total_cities, total_niches)
            next_city_idx = next_city_idx if next_city_idx is not None else computed_city
            next_niche_idx = next_niche_idx if next_niche_idx is not None else computed_niche

        logger.info(
            f"[STATE] Found previous session state (saved {timestamp}): "
            f"city='{city_names[last_city_idx]}' (index {last_city_idx}), "
            f"niche='{niche_names[last_niche_idx]}' (index {last_niche_idx}), "
            f"exhausted={was_exhausted}"
        )

        if force_next:
            adv_city, adv_niche = get_next_target(last_city_idx, last_niche_idx, total_cities, total_niches)
            logger.info(
                f"[STATE] --force-next enabled. Advancing rotation to "
                f"city '{city_names[adv_city]}' (index {adv_city}), niche '{niche_names[adv_niche]}' (index {adv_niche})."
            )
            return adv_city, adv_niche, False

        # Pick up exactly where execution left off
        if was_exhausted:
            logger.info(
                f"[STATE] Previous target was exhausted. Picking up with "
                f"city '{city_names[next_city_idx]}' (index {next_city_idx}), niche '{niche_names[next_niche_idx]}' (index {next_niche_idx})."
            )
            return next_city_idx, next_niche_idx, True
        else:
            logger.info(
                f"[STATE] Previous target ('{city_names[last_city_idx]}' + '{niche_names[last_niche_idx]}') "
                f"was interrupted when daily quota was met. Resuming at exact target."
            )
            return last_city_idx, last_niche_idx, False

    except Exception as e:
        logger.warning(f"[STATE] Failed to parse state file '{target_path}': {e}. Defaulting to index (0, 0).")

    return 0, 0, False

def save_state(
    state_file: Path,
    city_name: str,
    city_index: int,
    niche_name: str,
    niche_index: int,
    next_city_index: int,
    next_niche_index: int,
    target_exhausted: bool,
    successful_insertions: int,
    city_names: List[str],
    niche_names: List[str]
) -> None:
    """
    Persist current dual-rotation position (city, niche) and quota statistics to disk.
    """
    next_city_name = city_names[next_city_index] if 0 <= next_city_index < len(city_names) else "Unknown"
    next_niche_name = niche_names[next_niche_index] if 0 <= next_niche_index < len(niche_names) else "Unknown"

    state_payload = {
        "last_city": city_name,
        "last_city_index": city_index,
        "last_niche": niche_name,
        "last_niche_index": niche_index,
        "next_city": next_city_name,
        "next_city_index": next_city_index,
        "next_niche": next_niche_name,
        "next_niche_index": next_niche_index,
        "target_exhausted": target_exhausted,
        "successful_insertions_last_run": successful_insertions,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_payload, f, indent=2)
        logger.info(
            f"[STATE SAVED] Written to '{state_file.name}': "
            f"city='{city_name}', niche='{niche_name}', exhausted={target_exhausted} -> "
            f"next='{next_city_name}' + '{next_niche_name}' (indexes {next_city_index}, {next_niche_index})"
        )
    except Exception as e:
        logger.error(f"[STATE ERROR] Could not save state to '{state_file}': {e}")

# ==============================================================================
# Single Lead Processing
# ==============================================================================
async def process_single_lead(
    lead: Dict[str, Any],
    db: Database,
    extractor: WebExtractor,
    ai_engine: AIDraftingEngine
) -> Dict[str, Any]:
    """
    Process one lead: check duplicate, scrape, draft AI message, and insert into DB.
    """
    url = lead["website_url"]
    name = lead.get("business_name", "Unknown Business")
    dedupe_key = lead.get("dedupe_key") or make_dedupe_key(url)

    # 1. Pre-scrape Deduplication Check to save compute cycles
    if await db.lead_exists(dedupe_key):
        logger.info(f"[DEDUPLICATION] Skipping '{name}' ({url}) - already exists in database.")
        return {"status": "skipped", "lead_id": None, "url": url, "business_name": name}

    # 2. Stealth Scraping / Bypass
    strategy = lead.get("campaign_strategy")
    if strategy == "no_website":
        logger.info(f"[SCRAPING SKIPPED] '{name}' has no website. Bypassing Playwright extraction.")
        scraped_data = await extractor.scrape_lead(url, business_name=name, campaign_strategy="no_website")
    else:
        logger.info(f"[SCRAPING] Launching stealth Playwright extraction for: {url}")
        scraped_data = await extractor.scrape_lead(url, business_name=name)
        strategy = scraped_data.get("campaign_strategy", "legacy_redesign")

    async def disqualify(reason: str) -> Dict[str, Any]:
        # Stored (never shown in the dashboard) so later runs don't rediscover and rescrape it
        logger.info(f"[DISQUALIFIED] '{name}' ({url}): {reason}")
        await db.insert_lead({
            "business_name": name,
            "website_url": url,
            "dedupe_key": dedupe_key,
            "status": "disqualified",
            "city": lead.get("city"),
            "niche": lead.get("niche"),
            "raw_summary": reason,
            "campaign_strategy": strategy,
            "lead_score": scraped_data.get("lead_score"),
            "source": lead.get("source", "osm"),
        })
        return {"status": "disqualified", "lead_id": None, "url": url, "business_name": name, "reason": reason}

    scrape_status = scraped_data.get("scrape_status", "")
    if scrape_status == "error" or scrape_status.startswith("http_"):
        # Dead or erroring sites are usually closed businesses, not redesign prospects
        return await disqualify(f"Website failed to load ({scrape_status})")

    if strategy == "not_a_lead":
        return await disqualify(f"Modern site with little to fix (score {scraped_data.get('lead_score')})")

    # Merge any emails already discovered from OSM with scraped emails
    all_emails = sorted(set(lead.get("initial_emails", []) + scraped_data.get("emails", [])))
    instagram_url = scraped_data.get("instagram_url") or lead.get("instagram_url")
    linkedin_url = scraped_data.get("linkedin_url") or lead.get("linkedin_url")
    facebook_url = lead.get("facebook_url")

    if not (all_emails or lead.get("phone") or instagram_url or facebook_url):
        return await disqualify("No email, phone or social profile to contact")

    lead_context = {
        "business_name": name,
        "niche": lead.get("niche", "dentist"),
        "city": lead.get("city", "Austin"),
        "website_url": url,
        "instagram_url": instagram_url,
        "facebook_url": facebook_url,
        "linkedin_url": linkedin_url,
        "campaign_strategy": strategy,
        "technical_flaws": scraped_data.get("technical_flaws", [])
    }

    # 3. AI Drafting Engine via local Ollama
    logger.info(f"[AI DRAFTING] Requesting 3-sentence outreach draft for niche='{lead_context['niche']}', strategy='{strategy}'...")
    ai_message = await ai_engine.generate_outreach_message(
        lead_info=lead_context,
        site_summary=scraped_data.get("raw_summary", ""),
        strategy=strategy
    )

    # 4. Database Insertion with ON CONFLICT DO NOTHING
    record = {
        "business_name": name,
        "website_url": url,
        "emails": all_emails,
        "instagram_url": instagram_url,
        "linkedin_url": linkedin_url,
        "ai_outreach_message": ai_message,
        "status": "pending",
        "city": lead.get("city"),
        "niche": lead.get("niche"),
        "raw_summary": scraped_data.get("raw_summary"),
        "campaign_strategy": strategy,
        "dedupe_key": dedupe_key,
        "phone": lead.get("phone"),
        "facebook_url": facebook_url,
        "address": lead.get("address"),
        "lead_score": scraped_data.get("lead_score"),
        "technical_flaws": scraped_data.get("technical_flaws", []),
        "rating": lead.get("rating"),
        "review_count": lead.get("review_count"),
        "source": lead.get("source", "osm"),
    }

    lead_id = await db.insert_lead(record)
    return {
        "status": "inserted" if lead_id else "conflict_skipped",
        "lead_id": lead_id,
        "url": url,
        "business_name": name,
        "emails": all_emails,
        "instagram_url": record["instagram_url"],
        "linkedin_url": record["linkedin_url"],
        "campaign_strategy": strategy,
        "ai_message": ai_message
    }

# ==============================================================================
# Main Orchestrator with Dual City & Niche Rotation
# ==============================================================================
async def run_pipeline(
    daily_quota: int = DAILY_QUOTA,
    city_override: Optional[str] = None,
    niche_override: Optional[str] = None,
    test_url: Optional[str] = None,
    force_next: bool = False,
    reset_state: bool = False
):
    """
    Main autonomous orchestrator featuring nested dual rotation across
    TARGET_CITIES and TARGET_NICHES, daily quota enforcement, and local state memory.
    """
    logger.info("==================================================================")
    logger.info("Autonomous Dual City & Niche Lead Acquisition Pipeline Starting")
    logger.info(f"Target Daily Insertion Quota: {daily_quota}")
    logger.info(f"Available High-Ticket Niches: {len(TARGET_NICHES)}")
    logger.info(f"Available Global Cities: {len(TARGET_CITIES)}")
    logger.info("==================================================================")

    db = Database()
    extractor = WebExtractor()
    ai_engine = AIDraftingEngine()

    try:
        # Step 1: Database Initialization
        await db.init_schema()

        city_names = list(TARGET_CITIES.keys())
        niche_names = list(TARGET_NICHES)
        total_cities = len(city_names)
        total_niches = len(niche_names)

        # Handle direct test URL mode
        if test_url:
            logger.info(f"Running in TEST URL mode with target: {test_url}")
            test_lead = {
                "business_name": "Sample Test Business",
                "website_url": test_url,
                "city": city_override or "Austin",
                "niche": niche_override or "hvac",
                "initial_emails": []
            }
            res = await process_single_lead(test_lead, db, extractor, ai_engine)
            logger.info(f"Test run completed: {res}")
            return

        # Handle state reset
        if reset_state:
            if STATE_FILE.exists():
                STATE_FILE.unlink()
                logger.info(f"[STATE] Primary state file '{STATE_FILE.name}' deleted by --reset-state.")
            if LEGACY_STATE_FILE.exists():
                LEGACY_STATE_FILE.unlink()
                logger.info(f"[STATE] Legacy state file '{LEGACY_STATE_FILE.name}' deleted by --reset-state.")

        # Determine starting city and niche position from state or CLI overrides
        start_city_idx, start_niche_idx, _ = load_state(
            STATE_FILE,
            city_names,
            niche_names,
            force_next=force_next
        )

        if city_override:
            matched_c_idx = None
            for idx, c in enumerate(city_names):
                if c.lower() == city_override.lower():
                    matched_c_idx = idx
                    break
            if matched_c_idx is not None:
                start_city_idx = matched_c_idx
                logger.info(f"[CLI OVERRIDE] Starting city set to: '{city_names[start_city_idx]}' (index {start_city_idx}).")
            else:
                logger.warning(f"Specified city '{city_override}' not in TARGET_CITIES. Using index {start_city_idx}.")

        if niche_override:
            matched_n_idx = None
            for idx, n in enumerate(niche_names):
                if n.lower() == niche_override.lower():
                    matched_n_idx = idx
                    break
            if matched_n_idx is not None:
                start_niche_idx = matched_n_idx
                logger.info(f"[CLI OVERRIDE] Starting niche set to: '{niche_names[start_niche_idx]}' (index {start_niche_idx}).")
            else:
                logger.warning(f"Specified niche '{niche_override}' not in TARGET_NICHES. Using index {start_niche_idx}.")

        # Step 2: Dual Nested Rotation & Quota Loop
        successful_insertions = 0
        total_combinations = total_cities * total_niches
        combinations_visited = 0

        current_city_index = start_city_idx
        current_niche_index = start_niche_idx

        while successful_insertions < daily_quota and combinations_visited < total_combinations:
            current_city = city_names[current_city_index]
            current_niche = niche_names[current_niche_index]
            bbox = TARGET_CITIES[current_city]
            remaining_quota = daily_quota - successful_insertions

            logger.info("------------------------------------------------------------------")
            logger.info(f"TARGET MARKET [{current_city_index + 1}/{total_cities}]: {current_city}")
            logger.info(f"TARGET NICHE  [{current_niche_index + 1}/{total_niches}]: {current_niche.upper()}")
            logger.info(f"Bounding Box: {bbox}")
            logger.info(f"Acquisition Progress: {successful_insertions}/{daily_quota} new leads inserted ({remaining_quota} needed)")
            logger.info("------------------------------------------------------------------")

            # Extract sufficient candidates so duplicates don't prematurely exhaust the batch
            discovery_limit = max(30, remaining_quota * 3)
            leads_to_process = discover_leads(
                city=current_city,
                niche=current_niche,
                limit=discovery_limit,
                bbox=bbox
            )

            next_city_idx, next_niche_idx = get_next_target(
                current_city_index,
                current_niche_index,
                total_cities,
                total_niches
            )

            if not leads_to_process:
                logger.warning(
                    f"[TARGET EXHAUSTED] No candidate leads found for '{current_city}' + '{current_niche}' via Overpass API."
                )
                save_state(
                    STATE_FILE,
                    current_city, current_city_index,
                    current_niche, current_niche_index,
                    next_city_idx, next_niche_idx,
                    target_exhausted=True,
                    successful_insertions=successful_insertions,
                    city_names=city_names,
                    niche_names=niche_names
                )
                current_city_index, current_niche_index = next_city_idx, next_niche_idx
                combinations_visited += 1
                continue

            logger.info(
                f"Discovered {len(leads_to_process)} candidate leads for '{current_niche}' in '{current_city}'. "
                f"Commencing extraction..."
            )

            target_insertions_start = successful_insertions
            target_exhausted = True

            for idx, lead in enumerate(leads_to_process, 1):
                if successful_insertions >= daily_quota:
                    target_exhausted = False
                    break

                logger.info(f"[{current_city} | {current_niche}] Processing Lead {idx}/{len(leads_to_process)}: '{lead['business_name']}'")
                res = await process_single_lead(lead, db, extractor, ai_engine)

                # State Tracking: Only actual insertions count toward daily quota
                if res.get("status") == "inserted" and res.get("lead_id"):
                    successful_insertions += 1
                    logger.info(f"★ [QUOTA PROGRESS] Lead inserted [ID: {res['lead_id']}]: '{res['business_name']}' ({successful_insertions}/{daily_quota})")
                else:
                    logger.info(f"○ [QUOTA PROGRESS] Skipped lead '{res.get('business_name', 'Unknown')}' ({res.get('status')}) - does not count toward quota.")

                # If we just reached the quota, evaluate if target still has leads remaining
                if successful_insertions >= daily_quota:
                    if idx < len(leads_to_process):
                        target_exhausted = False
                    else:
                        target_exhausted = True
                    break

            target_new_leads = successful_insertions - target_insertions_start
            logger.info(f"Target '{current_city}' + '{current_niche}' session summary: {target_new_leads} new leads inserted.")

            # Check if daily quota was achieved
            if successful_insertions >= daily_quota:
                logger.info("==================================================================")
                logger.info(f"✓ DAILY QUOTA ACHIEVED: {successful_insertions}/{daily_quota} leads successfully inserted into PostgreSQL!")
                logger.info("==================================================================")
                final_next_city, final_next_niche = (
                    (next_city_idx, next_niche_idx) if target_exhausted else (current_city_index, current_niche_index)
                )
                save_state(
                    STATE_FILE,
                    current_city, current_city_index,
                    current_niche, current_niche_index,
                    final_next_city, final_next_niche,
                    target_exhausted=target_exhausted,
                    successful_insertions=successful_insertions,
                    city_names=city_names,
                    niche_names=niche_names
                )
                break

            # If quota not met, all candidates for (current_city, current_niche) were processed
            logger.warning(
                f"[AUTONOMOUS SWITCH] Target '{current_city}' + '{current_niche}' candidate URLs exhausted ({target_new_leads} new leads inserted). "
                f"Progress: {successful_insertions}/{daily_quota}. Advancing to next target in rotation..."
            )
            save_state(
                STATE_FILE,
                current_city, current_city_index,
                current_niche, current_niche_index,
                next_city_idx, next_niche_idx,
                target_exhausted=True,
                successful_insertions=successful_insertions,
                city_names=city_names,
                niche_names=niche_names
            )
            current_city_index, current_niche_index = next_city_idx, next_niche_idx
            combinations_visited += 1

        if successful_insertions < daily_quota and combinations_visited >= total_combinations:
            logger.warning(
                f"[ROTATION CYCLE COMPLETE] Visited all {total_combinations} (city, niche) combinations. "
                f"Total inserted: {successful_insertions}/{daily_quota}."
            )

        # Step 3: Summary Report
        logger.info("==================================================================")
        logger.info("Execution Finished. Recent leads in PostgreSQL database:")
        recent = await db.get_recent_leads(limit=5)
        for r in recent:
            logger.info(
                f"  [ID: {r['id']}] {r['business_name']} | City: {r['city']} | Niche: {r.get('niche')} | "
                f"Strategy: {r.get('campaign_strategy')} | URL: {r['website_url']}"
            )
            logger.info(f"    Emails: {r['emails']}")
            logger.info(f"    Socials: IG={r['instagram_url']}, LI={r['linkedin_url']}")
            logger.info(f"    Status: {r['status']}")
            logger.info("  " + "-"*50)

    finally:
        await db.close()

# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Autonomous Lead Extraction Pipeline with Dual City & Niche Rotation")
    parser.add_argument("--quota", type=int, default=DAILY_QUOTA, help=f"Daily insertion quota (default: {DAILY_QUOTA})")
    parser.add_argument("--city", type=str, default=None, help="City override to start rotation with")
    parser.add_argument("--niche", type=str, default=None, help="Niche override to start rotation with")
    parser.add_argument("--test-url", type=str, default=None, help="Direct test URL to scrape without Overpass discovery")
    parser.add_argument("--force-next", action="store_true", help="Force advancing to next target in rotation regardless of previous state")
    parser.add_argument("--reset-state", action="store_true", help="Reset local rotation memory and start from index (0, 0)")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database schema and exit")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if args.init_db:
        asyncio.run(Database().init_schema())
    else:
        asyncio.run(run_pipeline(
            daily_quota=args.quota,
            city_override=args.city,
            niche_override=args.niche,
            test_url=args.test_url,
            force_next=args.force_next,
            reset_state=args.reset_state
        ))
