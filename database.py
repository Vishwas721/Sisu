import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
import asyncpg
from config import config

logger = logging.getLogger("leads_pipeline.database")

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Establish asynchronous connection pool to PostgreSQL."""
        if not self.pool:
            logger.info(f"Connecting to PostgreSQL database: {config.DB_NAME} on {config.DB_HOST}:{config.DB_PORT}")
            self.pool = await asyncpg.create_pool(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                min_size=1,
                max_size=10
            )
            logger.info("Database connection pool established.")

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed.")

    async def init_schema(self):
        """Create the leads table and apply additive migrations from schema.sql."""
        if not self.pool:
            await self.connect()

        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)
        logger.info("Schema initialized and verified successfully.")

    async def lead_exists(self, dedupe_key: str) -> bool:
        """Check if a business (by dedupe key) is already stored to avoid redundant processing."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM leads WHERE dedupe_key = $1)",
                dedupe_key
            )
            return bool(val)

    async def count_leads_today(self) -> int:
        """New leads saved since midnight (database server time); disqualified ones don't count."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM leads WHERE status <> 'disqualified' "
                "AND created_at >= date_trunc('day', now())"
            )

    async def get_existing_keys(self) -> Set[str]:
        """All stored dedupe keys, used to filter discovery results before scraping."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT dedupe_key FROM leads WHERE dedupe_key IS NOT NULL")
            return {r["dedupe_key"] for r in rows}

    async def insert_lead(self, lead: Dict[str, Any]) -> Optional[int]:
        """
        Insert scraped lead; a duplicate website_url or dedupe_key is skipped via ON CONFLICT DO NOTHING.
        Accepts and stores campaign_strategy (no_website, legacy_redesign, ai_automation).
        Returns the new lead ID if inserted, or None if skipped due to conflict.
        """
        if not self.pool:
            await self.connect()

        query = """
        INSERT INTO leads (
            business_name,
            website_url,
            emails,
            instagram_url,
            linkedin_url,
            ai_outreach_message,
            status,
            city,
            niche,
            raw_summary,
            campaign_strategy,
            dedupe_key,
            phone,
            facebook_url,
            address,
            lead_score,
            technical_flaws,
            rating,
            review_count,
            source
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        ON CONFLICT DO NOTHING
        RETURNING id;
        """

        strategy = lead.get("campaign_strategy")

        async with self.pool.acquire() as conn:
            lead_id = await conn.fetchval(
                query,
                lead.get("business_name"),
                lead.get("website_url"),
                lead.get("emails", []),
                lead.get("instagram_url"),
                lead.get("linkedin_url"),
                lead.get("ai_outreach_message"),
                lead.get("status", "pending"),
                lead.get("city"),
                lead.get("niche"),
                lead.get("raw_summary"),
                strategy,
                lead.get("dedupe_key"),
                lead.get("phone"),
                lead.get("facebook_url"),
                lead.get("address"),
                lead.get("lead_score"),
                lead.get("technical_flaws", []),
                lead.get("rating"),
                lead.get("review_count"),
                lead.get("source"),
            )
            if lead_id:
                logger.info(
                    f"Inserted new lead [ID: {lead_id}] (strategy: {strategy}): "
                    f"{lead.get('business_name')} ({lead.get('website_url')})"
                )
            else:
                logger.warning(f"Duplicate lead skipped via ON CONFLICT: {lead.get('website_url')}")
            return lead_id

    async def get_lead_by_url(self, website_url: str) -> Optional[Dict[str, Any]]:
        """Retrieve lead record by website_url."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM leads WHERE website_url = $1", website_url)
            return dict(row) if row else None

    async def get_recent_leads(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve most recent leads."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM leads ORDER BY id DESC LIMIT $1", limit)
            return [dict(r) for r in rows]
