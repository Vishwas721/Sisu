'use server';

import {
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

export async function getRunSuggestions(): Promise<{ cities: string[]; niches: string[] }> {
  return getTargetSuggestions();
}
