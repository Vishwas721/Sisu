'use server';

import pool from '@/lib/db';
import {
  readDailyCap,
  startRun,
  stopRun,
  getStatus,
  getTargetSuggestions,
  type RunMode,
  type RunStatus,
} from '@/lib/pipelineRunner';

// Letters (any language), digits, spaces and light punctuation: "St. John's", "Washington DC", "auto repair"
const SAFE_TEXT = /^[\p{L}\p{N} .,'&()-]{0,80}$/u;

function cleanField(value: unknown, label: string): string {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!SAFE_TEXT.test(text)) {
    throw new Error(`${label} can only contain letters, numbers, spaces and . , ' & ( ) -`);
  }
  return text;
}

/**
 * Start the Python pipeline.
 * - target: exactly this city + niche (both required)
 * - random: random city/niche pairs until the quota is met; a filled-in field stays fixed
 */
export async function startPipelineRun(input: {
  mode: RunMode;
  city?: string;
  niche?: string;
  quota?: number;
}): Promise<{ ok: boolean; status?: RunStatus; error?: string }> {
  try {
    const mode: RunMode = input.mode === 'random' ? 'random' : 'target';
    const city = cleanField(input.city, 'City');
    const niche = cleanField(input.niche, 'Niche');
    const quota = Math.min(100, Math.max(1, Math.floor(Number(input.quota) || 15)));

    if (mode === 'target' && (!city || !niche)) {
      throw new Error('Enter both a city and a niche, or use Random.');
    }
    const usage = await getDailyUsage();
    if (usage.left === 0) {
      throw new Error(`Daily cap reached (${usage.today}/${usage.cap} today). Raise DAILY_LEAD_CAP in .env to allow more.`);
    }
    return { ok: true, status: startRun({ mode, city, niche, quota }) };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}

export async function stopPipelineRun(): Promise<void> {
  stopRun();
}

export async function getPipelineStatus(): Promise<RunStatus> {
  return getStatus();
}

export interface DailyUsage {
  today: number;
  cap: number; // 0 = no cap
  left: number | null; // null when there is no cap
}

/** Same count the pipeline uses: non-disqualified leads created since midnight (DB time). */
export async function getDailyUsage(): Promise<DailyUsage> {
  const cap = readDailyCap();
  const result = await pool.query(
    "SELECT COUNT(*) AS n FROM leads WHERE status <> 'disqualified' AND created_at >= date_trunc('day', now())"
  );
  const today = parseInt(result.rows[0]?.n ?? '0', 10);
  return { today, cap, left: cap > 0 ? Math.max(0, cap - today) : null };
}

export async function getRunSuggestions(): Promise<{ cities: string[]; niches: string[] }> {
  return getTargetSuggestions();
}
