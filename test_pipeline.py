import asyncio
import logging
from database import Database
from extractor import WebExtractor
from ai_drafter import AIDraftingEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_pipeline")

async def test_full_flow():
    logger.info("=== Starting Verification Test ===")
    
    # 1. Test Database Initialization
    logger.info("1. Testing Database Connection & Schema Initialization...")
    db = Database()
    await db.init_schema()
    logger.info("-> Database schema successfully initialized.")

    # 2. Test Ollama AI Drafting Engine
    logger.info("2. Testing Local Ollama AI Drafting Engine...")
    ai_engine = AIDraftingEngine()
    test_lead_info = {
        "business_name": "Austin Dental Care Clinic",
        "niche": "dental clinic",
        "city": "Austin, Texas",
        "technical_flaws": ["Missing responsive viewport tag", "Slow initial page load time (6.2s)", "Missing search meta description"]
    }
    test_summary = (
        "Austin Dental Care Clinic is a family-owned dental office providing cosmetic dentistry, "
        "orthodontics, and teeth whitening in Austin, TX. The website lacks mobile viewport configuration "
        "and takes over 6 seconds to load assets."
    )
    message = await ai_engine.generate_outreach_message(test_lead_info, test_summary)
    logger.info(f"-> Ollama Output:\n'{message}'")
    
    # Count sentences
    sentence_count = len([s for s in message.replace("!", ".").replace("?", ".").split(".") if s.strip()])
    logger.info(f"-> Sentence Count: {sentence_count}")

    # 3. Test Playwright Stealth Scraping against sample URL
    logger.info("3. Testing Playwright Stealth Web Extractor...")
    extractor = WebExtractor()
    sample_url = "https://example.com"
    scraped = await extractor.scrape_lead(sample_url, business_name="Example Practice")
    await extractor.close()
    assert scraped["scrape_status"] == "success", f"Scrape failed: {scraped['raw_summary']}"
    logger.info(f"-> Scraped data from {sample_url}:")
    logger.info(f"   Status: {scraped['scrape_status']}")
    logger.info(f"   Load Time: {scraped['load_time_sec']}s")
    logger.info(f"   Detected Flaws: {scraped['technical_flaws']}")
    logger.info(f"   Raw summary excerpt: {scraped['raw_summary'][:150]}...")

    # 4. Test Database Insertion with Deduplication
    logger.info("4. Testing Database Insertion & ON CONFLICT DO NOTHING...")
    test_record = {
        "business_name": "Austin Dental Care Clinic",
        "website_url": "https://austindentalcare-test-sample.com",
        "dedupe_key": "austindentalcare-test-sample.com",
        "emails": ["contact@austindentalcare-test.com", "info@austindentalcare-test.com"],
        "instagram_url": "https://instagram.com/austindentalcare",
        "linkedin_url": "https://linkedin.com/company/austindentalcare",
        "ai_outreach_message": message,
        "status": "pending",
        "city": "Austin",
        "niche": "dentist",
        "raw_summary": test_summary
    }

    # Clean up test record if it exists from previous test
    async with db.pool.acquire() as conn:
        await conn.execute("DELETE FROM leads WHERE website_url = $1", test_record["website_url"])

    # First insertion - should succeed
    lead_id_1 = await db.insert_lead(test_record)
    logger.info(f"-> First insertion result: ID={lead_id_1} (Success: {lead_id_1 is not None})")
    assert lead_id_1 is not None, "First insertion should return an ID"

    # Second insertion with same website_url - should be skipped due to UNIQUE constraint & ON CONFLICT DO NOTHING
    logger.info("-> Testing duplicate insertion with identical website_url...")
    lead_id_2 = await db.insert_lead(test_record)
    logger.info(f"-> Duplicate insertion result: ID={lead_id_2} (Expected: None)")
    assert lead_id_2 is None, "Duplicate insertion should return None due to ON CONFLICT DO NOTHING"

    # Verify record in database
    retrieved = await db.get_lead_by_url(test_record["website_url"])
    logger.info(f"-> Retrieved Record from DB: ID={retrieved['id']}, Name={retrieved['business_name']}, Emails={retrieved['emails']}, Status={retrieved['status']}")

    await db.close()
    logger.info("=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
