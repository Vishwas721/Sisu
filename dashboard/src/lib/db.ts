import { Pool } from 'pg';

export interface Lead {
  id: number;
  business_name: string;
  website_url: string | null;
  city: string | null;
  email: string | null;
  instagram_url: string | null;
  linkedin_url: string | null;
  facebook_url: string | null;
  phone: string | null;
  lead_score: number | null;
  rating: number | null;
  review_count: number | null;
  ai_drafted_message: string | null;
  campaign_strategy: 'no_website' | 'legacy_redesign' | 'ai_automation' | string;
  status: 'pending' | 'contacted' | 'rejected' | string;
  created_at?: string;
}

declare global {
  // eslint-disable-next-line no-var
  var __pgPool: Pool | undefined;
}

// Singleton PostgreSQL connection pool for Next.js App Router
const pool: Pool =
  global.__pgPool ??
  new Pool({
    host: process.env.DB_HOST || '127.0.0.1',
    port: parseInt(process.env.DB_PORT || '5432', 10),
    database: process.env.DB_NAME || 'leads_pipeline',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD,
    connectionString: process.env.DATABASE_URL,
    max: 10,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
  });

if (process.env.NODE_ENV !== 'production') {
  global.__pgPool = pool;
}

export default pool;
