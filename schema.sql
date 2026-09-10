-- ==============================================================================
-- PostgreSQL Schema for Leads Pipeline
-- ==============================================================================

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

-- Migration safety for existing tables
ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_strategy VARCHAR(50);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_leads_website_url ON leads (website_url);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_campaign_strategy ON leads (campaign_strategy);

-- Optional trigger function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS trigger_leads_updated_at ON leads;
CREATE TRIGGER trigger_leads_updated_at
BEFORE UPDATE ON leads
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
