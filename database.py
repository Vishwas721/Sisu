import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
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
        """Initialize and migrate database schema to include campaign_strategy."""
        if not self.pool:
            await self.connect()

        if SCHEMA_FILE.exists():
            with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)
                # Ensure campaign_strategy column and index exist on existing tables
                await conn.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_strategy VARCHAR(50);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign_strategy ON leads (campaign_strategy);")
            logger.info("Schema initialized and verified successfully.")
        else:
            # Fallback inline schema creation
            schema_sql = """
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                business_name VARCHAR(255) NOT NULL,
                website_url TEXT NOT NULL UNIQUE,
                emails TEXT[] DEFAULT '{}',
                instagram_url TEXT,
                linkedin_url TEXT,
                ai_outreach_message TEXT,
                status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                city VARCHAR(100),
                niche VARCHAR(100),
                raw_summary TEXT,
                campaign_strategy VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_leads_website_url ON leads (website_url);
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
            CREATE INDEX IF NOT EXISTS idx_leads_campaign_strategy ON leads (campaign_strategy);
            """
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)
                await conn.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_strategy VARCHAR(50);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign_strategy ON leads (campaign_strategy);")
            logger.info("Schema initialized from fallback definition.")

    async def website_exists(self, website_url: str) -> bool:
        """Check if website_url has already been stored to avoid redundant processing."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM leads WHERE website_url = $1)",
                website_url
            )
            return bool(val)

    async def insert_lead(self, lead: Dict[str, Any]) -> Optional[int]:
        """
        Insert scraped lead with deduplication using ON CONFLICT DO NOTHING.
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
            campaign_strategy
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (website_url) DO NOTHING
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
                strategy
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
