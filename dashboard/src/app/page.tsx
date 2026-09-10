import React from 'react';
import Header from '@/components/Header';
import LeadDashboard from '@/components/LeadDashboard';
import { getLeadsByStrategy, getStrategyStats } from '@/app/actions';
import { Lead } from '@/lib/db';
import { AlertTriangle, Database } from 'lucide-react';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export default async function HomePage() {
  let initialLeads: Lead[] = [];
  let stats = {
    no_website: 0,
    legacy_redesign: 0,
    ai_automation: 0,
    total_pending: 0,
    total_contacted: 0,
  };
  let error: string | null = null;

  try {
    // 1. Fetch live strategy statistics for tab badges
    stats = await getStrategyStats();

    // 2. Fetch initial batch of up to 15 pending leads for default tab (No Website)
    initialLeads = await getLeadsByStrategy('no_website', 15);
  } catch (err: unknown) {
    console.error('Failed to load initial data in page.tsx:', err);
    error = (err as Error).message || 'Could not connect to PostgreSQL database.';
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <Header />

      {/* Main Command Center */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        {error ? (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-8 text-center backdrop-blur-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h2 className="mt-4 text-base font-semibold text-rose-300">Database Connection Error</h2>
            <p className="mt-1 text-xs text-rose-400/80 max-w-md mx-auto">{error}</p>
            <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-400">
              <Database className="h-4 w-4" />
              <span>Ensure PostgreSQL is running on 127.0.0.1:5432 and credentials in .env.local are correct.</span>
            </div>
          </div>
        ) : (
          <LeadDashboard initialLeads={initialLeads} initialStats={stats} />
        )}
      </main>
    </div>
  );
}
