'use server';

import pool, { Lead } from '@/lib/db';
import { revalidatePath } from 'next/cache';

export type StrategyFilter = 'no_website' | 'legacy_redesign' | 'ai_automation' | 'all';

export interface StrategyStats {
  no_website: number;
  legacy_redesign: number;
  ai_automation: number;
  total_pending: number;
  total_contacted: number;
}

/**
 * Filtered Data Fetching:
 * Queries PostgreSQL for pending leads, filtered by the currently selected tab (strategy).
 * Limits the total displayed to a maximum of 15 pending leads to maintain the daily quota.
 */
export async function getLeadsByStrategy(
  strategy: StrategyFilter = 'no_website',
  limit: number = 15
): Promise<Lead[]> {
  try {
    let whereCondition = "status = 'pending'";
    const queryParams: (string | number)[] = [];

    if (strategy === 'no_website') {
      whereCondition += " AND campaign_strategy = 'no_website'";
    } else if (strategy === 'legacy_redesign') {
      whereCondition += " AND (campaign_strategy = 'legacy_redesign' OR campaign_strategy IS NULL)";
    } else if (strategy === 'ai_automation') {
      whereCondition += " AND campaign_strategy = 'ai_automation'";
    }
    // 'all' includes all pending leads across any strategy

    queryParams.push(limit);

    const query = `
      SELECT 
        id,
        business_name,
        website_url,
        city,
        COALESCE(
          NULLIF(to_jsonb(leads)->>'email', ''),
          CASE 
            WHEN to_jsonb(leads)?'emails' AND jsonb_typeof(to_jsonb(leads)->'emails') = 'array'
            THEN array_to_string(emails, ', ')
            ELSE ''
          END
        ) AS email,
        instagram_url,
        linkedin_url,
        COALESCE(
          NULLIF(to_jsonb(leads)->>'ai_drafted_message', ''),
          NULLIF(to_jsonb(leads)->>'ai_outreach_message', ''),
          ''
        ) AS ai_drafted_message,
        COALESCE(to_jsonb(leads)->>'campaign_strategy', 'legacy_redesign') AS campaign_strategy,
        status,
        created_at
      FROM leads
      WHERE ${whereCondition}
      ORDER BY created_at ASC
      LIMIT $1;
    `;

    const result = await pool.query(query, queryParams);

    return result.rows.map((row) => ({
      id: row.id,
      business_name: row.business_name || 'Unnamed Business',
      website_url: row.website_url || null,
      city: row.city || null,
      email: row.email || null,
      instagram_url: row.instagram_url || null,
      linkedin_url: row.linkedin_url || null,
      ai_drafted_message: row.ai_drafted_message || null,
      campaign_strategy: row.campaign_strategy || 'legacy_redesign',
      status: row.status || 'pending',
      created_at: row.created_at ? new Date(row.created_at).toISOString() : new Date().toISOString(),
    }));
  } catch (error) {
    console.error('[DATABASE ERROR] Failed to fetch leads by strategy:', error);
    throw new Error('Unable to retrieve categorized leads from PostgreSQL.');
  }
}

/**
 * Fetch counts of pending leads grouped by each of the 3 strategies
 * for live tab badges.
 */
export async function getStrategyStats(): Promise<StrategyStats> {
  try {
    const query = `
      SELECT 
        COUNT(*) FILTER (WHERE status = 'pending' AND campaign_strategy = 'no_website') AS no_website_count,
        COUNT(*) FILTER (WHERE status = 'pending' AND (campaign_strategy = 'legacy_redesign' OR campaign_strategy IS NULL)) AS legacy_redesign_count,
        COUNT(*) FILTER (WHERE status = 'pending' AND campaign_strategy = 'ai_automation') AS ai_automation_count,
        COUNT(*) FILTER (WHERE status = 'pending') AS total_pending,
        COUNT(*) FILTER (WHERE status = 'contacted') AS total_contacted
      FROM leads;
    `;

    const result = await pool.query(query);
    const row = result.rows[0];

    return {
      no_website: parseInt(row?.no_website_count || '0', 10),
      legacy_redesign: parseInt(row?.legacy_redesign_count || '0', 10),
      ai_automation: parseInt(row?.ai_automation_count || '0', 10),
      total_pending: parseInt(row?.total_pending || '0', 10),
      total_contacted: parseInt(row?.total_contacted || '0', 10),
    };
  } catch (error) {
    console.error('[DATABASE ERROR] Failed to fetch strategy stats:', error);
    return {
      no_website: 0,
      legacy_redesign: 0,
      ai_automation: 0,
      total_pending: 0,
      total_contacted: 0,
    };
  }
}

/**
 * State Mutation: The Spark Dispatch Action
 * Updates a specific lead's status to 'contacted' in the PostgreSQL database.
 */
export async function markLeadContacted(id: number): Promise<{ success: boolean; id: number; message?: string }> {
  try {
    const query = `
      UPDATE leads
      SET status = 'contacted', updated_at = CURRENT_TIMESTAMP
      WHERE id = $1
      RETURNING id, status;
    `;

    const result = await pool.query(query, [id]);

    if (result.rowCount === 0) {
      return { success: false, id, message: `Lead #${id} not found.` };
    }

    revalidatePath('/');
    return { success: true, id };
  } catch (error) {
    return { success: false, id, message: (error as Error).message };
  }
}

/**
 * Bulk State Mutation: Bulk Spark Dispatch Action
 * Executes a single PostgreSQL UPDATE query that changes the status to 'contacted'
 * for all IDs passed in the array.
 */
export async function markAllAsContacted(
  leadIds: number[]
): Promise<{ success: boolean; count: number; ids: number[]; message?: string }> {
  if (!leadIds || leadIds.length === 0) {
    return { success: true, count: 0, ids: [] };
  }

  try {
    const query = `
      UPDATE leads
      SET status = 'contacted', updated_at = CURRENT_TIMESTAMP
      WHERE id = ANY($1::int[])
      RETURNING id, status;
    `;

    const result = await pool.query(query, [leadIds]);

    revalidatePath('/');
    return {
      success: true,
      count: result.rowCount ?? 0,
      ids: result.rows.map((row: { id: number }) => row.id),
    };
  } catch (error) {
    console.error('[DATABASE ERROR] Failed to mark leads as contacted in bulk:', error);
    return {
      success: false,
      count: 0,
      ids: [],
      message: (error as Error).message || 'Failed to bulk update leads in PostgreSQL.',
    };
  }
}

