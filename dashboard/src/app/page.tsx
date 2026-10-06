'use client';

import React, { useState, useEffect, useTransition, useCallback } from 'react';
import Header from '@/components/Header';
import LeadCard from '@/components/LeadCard';
import RunPanel from '@/components/RunPanel';
import {
  getLeadsByStrategy,
  getStrategyStats,
  markAllAsContacted,
  StrategyFilter,
  StrategyStats,
} from '@/app/actions';
import { Lead } from '@/lib/db';
import {
  Sparkles,
  RefreshCw,
  Search,
  CheckCheck,
  Zap,
  TrendingUp,
  Inbox,
  Filter,
  Share2,
  Wrench,
  Cpu,
  Loader2,
  Copy,
  AlertCircle,
  AlertTriangle,
  Database,
} from 'lucide-react';

type TabKey = 'no_website' | 'legacy_redesign' | 'ai_automation';

interface TabDefinition {
  id: TabKey;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  activeBg: string;
  badgeBg: string;
}

const STRATEGY_TABS: TabDefinition[] = [
  {
    id: 'no_website',
    label: 'No Website',
    description: 'Social profile presence only (Instagram / Facebook)',
    icon: Share2,
    color: 'text-fuchsia-400',
    activeBg: 'bg-fuchsia-500/10 border-fuchsia-500/50 text-white shadow-lg shadow-fuchsia-500/10',
    badgeBg: 'bg-fuchsia-500/20 text-fuchsia-300 border border-fuchsia-500/30',
  },
  {
    id: 'legacy_redesign',
    label: 'Legacy Redesign',
    description: 'Outdated design, HTTP, or non-responsive mobile DOM',
    icon: Wrench,
    color: 'text-amber-400',
    activeBg: 'bg-amber-500/10 border-amber-500/50 text-white shadow-lg shadow-amber-500/10',
    badgeBg: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
  },
  {
    id: 'ai_automation',
    label: 'AI Automations',
    description: 'Modern sites lacking self-serve scheduling / AI chatbots',
    icon: Cpu,
    color: 'text-emerald-400',
    activeBg: 'bg-emerald-500/10 border-emerald-500/50 text-white shadow-lg shadow-emerald-500/10',
    badgeBg: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  },
];

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabKey>('no_website');
  const [leadsByTab, setLeadsByTab] = useState<Record<TabKey, Lead[]>>({
    no_website: [],
    legacy_redesign: [],
    ai_automation: [],
  });
  const [loadedTabs, setLoadedTabs] = useState<Record<TabKey, boolean>>({
    no_website: false,
    legacy_redesign: false,
    ai_automation: false,
  });
  const [stats, setStats] = useState<StrategyStats>({
    no_website: 0,
    legacy_redesign: 0,
    ai_automation: 0,
    total_pending: 0,
    total_contacted: 0,
  });
  const [isLoadingInitial, setIsLoadingInitial] = useState(true);
  const [initialError, setInitialError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedChannel, setSelectedChannel] = useState<'all' | 'email' | 'linkedin' | 'instagram'>('all');
  const [lastDispatched, setLastDispatched] = useState<string | null>(null);

  // Bulk Dispatch States
  const [isBulkDispatching, setIsBulkDispatching] = useState(false);
  const [isBulkDispatched, setIsBulkDispatched] = useState(false);
  const [bulkToastMessage, setBulkToastMessage] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const [isPending, startTransition] = useTransition();

  // Load initial batch of 15 leads for default strategy tab + live stats
  useEffect(() => {
    let isMounted = true;

    async function loadDashboardData() {
      try {
        setIsLoadingInitial(true);
        setInitialError(null);

        const [initialStats, initialBatch] = await Promise.all([
          getStrategyStats(),
          getLeadsByStrategy('no_website', 15),
        ]);

        if (isMounted) {
          setStats(initialStats);
          setLeadsByTab((prev) => ({ ...prev, no_website: initialBatch }));
          setLoadedTabs((prev) => ({ ...prev, no_website: true }));
          setIsLoadingInitial(false);
        }
      } catch (err: unknown) {
        console.error('Failed to load initial dashboard data:', err);
        if (isMounted) {
          setInitialError((err as Error).message || 'Could not connect to PostgreSQL database.');
          setIsLoadingInitial(false);
        }
      }
    }

    loadDashboardData();

    return () => {
      isMounted = false;
    };
  }, []);

  const currentLeads = leadsByTab[activeTab] || [];

  // Tab switcher with dynamic data fetching
  const handleTabChange = (tabId: TabKey) => {
    setActiveTab(tabId);

    if (!loadedTabs[tabId]) {
      startTransition(async () => {
        try {
          const fetched = await getLeadsByStrategy(tabId, 15);
          setLeadsByTab((prev) => ({ ...prev, [tabId]: fetched }));
          setLoadedTabs((prev) => ({ ...prev, [tabId]: true }));
        } catch (err) {
          console.error(`Failed to fetch leads for tab ${tabId}:`, err);
        }
      });
    }
  };

  // Re-fetch current strategy batch + refresh stats
  const handleRefreshCurrentTab = () => {
    startTransition(async () => {
      try {
        const [freshLeads, freshStats] = await Promise.all([
          getLeadsByStrategy(activeTab, 15),
          getStrategyStats(),
        ]);
        setLeadsByTab((prev) => ({ ...prev, [activeTab]: freshLeads }));
        setStats(freshStats);
      } catch (err) {
        console.error('Failed to refresh tab:', err);
      }
    });
  };

  // After a pipeline run: reload the visible tab and stats, and refetch other tabs when opened
  const handleRunFinished = useCallback(() => {
    setLoadedTabs({ no_website: false, legacy_redesign: false, ai_automation: false, [activeTab]: true });
    handleRefreshCurrentTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Optimistic handler for single lead dispatch from LeadCard
  const handleLeadContacted = (id: number, businessName: string) => {
    setLeadsByTab((prev) => ({
      ...prev,
      [activeTab]: prev[activeTab].filter((lead) => lead.id !== id),
    }));

    setStats((prev) => ({
      ...prev,
      [activeTab]: Math.max(0, prev[activeTab] - 1),
      total_pending: Math.max(0, prev.total_pending - 1),
      total_contacted: prev.total_contacted + 1,
    }));

    setLastDispatched(businessName);
    setTimeout(() => {
      setLastDispatched((current) => (current === businessName ? null : current));
    }, 4000);
  };

  // Filtered leads based on search term and channel chips
  const filteredLeads = currentLeads.filter((lead) => {
    const matchesSearch =
      lead.business_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (lead.city && lead.city.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (lead.email && lead.email.toLowerCase().includes(searchTerm.toLowerCase()));

    if (!matchesSearch) return false;

    if (selectedChannel === 'email') return !!lead.email;
    if (selectedChannel === 'linkedin') return !!lead.linkedin_url;
    if (selectedChannel === 'instagram') return !!lead.instagram_url;

    return true;
  });

  /**
   * Client-Side Bulk Dispatch Logic:
   * 1. Iterates over currently visible leads state
   * 2. Formats each lead into LLM-structured payload:
   *    --- LEAD [Index] ---
   *    Business: [business_name]
   *    Target Email: [email] (If no email, print the Instagram/Facebook URL)
   *    Message:
   *    [ai_drafted_message]
   *    -------------------
   * 3. Copies combined string to user clipboard
   * 4. Calls Server Action markAllAsContacted(leadIds) to update PostgreSQL status
   * 5. Optimistically clears the UI grid and updates counters
   */
  const handleBulkDispatch = async () => {
    const leadsToDispatch = filteredLeads;
    if (leadsToDispatch.length === 0 || isBulkDispatching) return;

    setIsBulkDispatching(true);
    setBulkError(null);

    const leadIds = leadsToDispatch.map((lead) => lead.id);
    const count = leadsToDispatch.length;

    // Format all displayed leads into structured LLM string
    const formattedPayload = leadsToDispatch
      .map((lead, idx) => {
        const targetContact =
          lead.email?.trim() ||
          lead.instagram_url?.trim() ||
          (lead.website_url &&
          (lead.website_url.includes('facebook.com') || lead.website_url.includes('instagram.com'))
            ? lead.website_url.trim()
            : null) ||
          lead.website_url?.trim() ||
          'No email or social profile URL available';

        const message = lead.ai_drafted_message?.trim() || 'No AI message drafted for this lead.';

        return [
          `--- LEAD ${idx + 1} ---`,
          `Business: ${lead.business_name}`,
          `Target Email: ${targetContact}`,
          `Message:`,
          `${message}`,
          `-------------------`,
        ].join('\n');
      })
      .join('\n\n');

    try {
      // 1. Copy formatted text directly to clipboard
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(formattedPayload);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = formattedPayload;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }

      // 2. Optimistically clear the UI grid for the current view
      setLeadsByTab((prev) => ({
        ...prev,
        [activeTab]: prev[activeTab].filter((lead) => !leadIds.includes(lead.id)),
      }));

      // 3. Optimistically update KPI stats
      setStats((prev) => ({
        ...prev,
        [activeTab]: Math.max(0, prev[activeTab] - count),
        total_pending: Math.max(0, prev.total_pending - count),
        total_contacted: prev.total_contacted + count,
      }));

      setIsBulkDispatched(true);
      setBulkToastMessage(`Copied ${count} leads to Spark clipboard & marked contacted in PostgreSQL!`);

      // 4. Trigger Server Action to update all IDs in PostgreSQL in a single query
      const result = await markAllAsContacted(leadIds);

      if (!result.success) {
        throw new Error(result.message || 'Bulk update failed in PostgreSQL.');
      }

      setTimeout(() => {
        setIsBulkDispatched(false);
      }, 4000);

      setTimeout(() => {
        setBulkToastMessage(null);
      }, 5000);
    } catch (err: unknown) {
      console.error('Bulk dispatch error:', err);
      setBulkError((err as Error).message || 'Failed to bulk dispatch leads.');
    } finally {
      setIsBulkDispatching(false);
    }
  };

  const activeTabDef = STRATEGY_TABS.find((t) => t.id === activeTab)!;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <Header />

      {/* Main Command Center */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        {initialError ? (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-8 text-center backdrop-blur-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h2 className="mt-4 text-base font-semibold text-rose-300">Database Connection Error</h2>
            <p className="mt-1 text-xs text-rose-400/80 max-w-md mx-auto">{initialError}</p>
            <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-400">
              <Database className="h-4 w-4" />
              <span>Ensure PostgreSQL is running on 127.0.0.1:5432 and credentials in .env.local are correct.</span>
            </div>
          </div>
        ) : isLoadingInitial ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/40 p-24 text-center">
            <Loader2 className="h-10 w-10 animate-spin text-indigo-400" />
            <p className="mt-4 text-sm text-slate-300 font-medium">Connecting to PostgreSQL & Loading Daily 15 Leads...</p>
            <p className="mt-1 text-xs text-slate-500">Preparing campaign strategies and AI drafts</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Toast Notification for Single Lead Dispatch */}
            {lastDispatched && (
              <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl border border-emerald-500/40 bg-slate-900/95 px-4 py-3 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                  <CheckCheck className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-white">Spark Dossier Copied & Dispatched!</p>
                  <p className="text-xs text-slate-400">
                    <span className="font-medium text-emerald-300">{lastDispatched}</span> updated to{' '}
                    <span className="text-white font-mono">contacted</span> in PostgreSQL.
                  </p>
                </div>
              </div>
            )}

            {/* Toast Notification for Spark Bulk Dispatch */}
            {bulkToastMessage && (
              <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl border border-emerald-500/40 bg-slate-900/95 px-5 py-3.5 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                  <CheckCheck className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-white">Spark Bulk Dossier Copied!</p>
                  <p className="text-xs text-slate-400">{bulkToastMessage}</p>
                </div>
              </div>
            )}

            {/* Toast Notification for Bulk Error */}
            {bulkError && (
              <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl border border-rose-500/40 bg-slate-900/95 px-5 py-3.5 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-rose-500/20 text-rose-400">
                  <AlertCircle className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-rose-300">Bulk Dispatch Failed</p>
                  <p className="text-xs text-rose-400/80">{bulkError}</p>
                </div>
              </div>
            )}

            {/* Start a pipeline run for a typed or random city + niche */}
            <RunPanel onRunFinished={handleRunFinished} />

            {/* KPI Stats Ribbon */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Active Tab Quota Progress */}
              <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">
                    {activeTabDef.label} Batch
                  </span>
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-400">
                    <Zap className="h-4 w-4" />
                  </div>
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">{currentLeads.length}</span>
                  <span className="text-xs text-slate-400">/ 15 in active view</span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
                    style={{ width: `${Math.min(100, (currentLeads.length / 15) * 100)}%` }}
                  />
                </div>
              </div>

              {/* Total Database Pending */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">Total Uncontacted Pipeline</span>
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500/10 text-amber-400">
                    <Inbox className="h-4 w-4" />
                  </div>
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-amber-400">{stats.total_pending}</span>
                  <span className="text-xs text-slate-400">leads awaiting outreach</span>
                </div>
              </div>

              {/* Total Contacted */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">Total Dispatched / Contacted</span>
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-400">
                    <TrendingUp className="h-4 w-4" />
                  </div>
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-emerald-400">{stats.total_contacted}</span>
                  <span className="text-xs text-slate-400">leads reached</span>
                </div>
              </div>
            </div>

            {/* Primary Tab Navigation & Bulk Dispatch Action Bar */}
            <div className="flex flex-col xl:flex-row items-stretch xl:items-center justify-between gap-3">
              {/* Strategy Tab Selector */}
              <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900/80 p-2 backdrop-blur-md">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  {STRATEGY_TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    const count = stats[tab.id];

                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => handleTabChange(tab.id)}
                        className={`flex items-center justify-between rounded-xl border p-3.5 transition-all text-left cursor-pointer ${
                          isActive
                            ? tab.activeBg
                            : 'border-slate-800/80 bg-slate-950/40 text-slate-400 hover:border-slate-700 hover:bg-slate-900/60 hover:text-slate-200'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                              isActive ? 'bg-white/10 text-white' : 'bg-slate-800/80 ' + tab.color
                            }`}
                          >
                            <Icon className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-semibold tracking-tight">{tab.label}</span>
                            </div>
                            <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                              {tab.description}
                            </p>
                          </div>
                        </div>

                        {/* Tab Count Badge */}
                        <span
                          className={`ml-2 inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold shrink-0 ${
                            isActive
                              ? tab.badgeBg
                              : 'bg-slate-800/80 text-slate-400 border border-slate-700/50'
                          }`}
                        >
                          {count} leads
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Global Prominent "Bulk Dispatch to Spark" Button */}
              <button
                type="button"
                onClick={handleBulkDispatch}
                disabled={isBulkDispatching || filteredLeads.length === 0}
                className={`group relative flex items-center justify-center gap-3 rounded-2xl px-6 py-4 text-sm font-bold text-white shadow-xl transition-all duration-300 cursor-pointer border shrink-0 ${
                  isBulkDispatched
                    ? 'bg-emerald-600 border-emerald-400/80 shadow-emerald-600/30'
                    : 'bg-gradient-to-r from-amber-500 via-orange-500 to-rose-600 hover:from-amber-400 hover:via-orange-400 hover:to-rose-500 border-amber-300/40 shadow-orange-500/25 hover:shadow-orange-500/40 hover:scale-[1.02] active:scale-[0.98]'
                } disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none`}
              >
                {isBulkDispatching ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin text-white" />
                    <span>Dispatching All ({filteredLeads.length})...</span>
                  </>
                ) : isBulkDispatched ? (
                  <>
                    <CheckCheck className="h-5 w-5 text-white animate-bounce" />
                    <span>Dispatched & Copied All!</span>
                  </>
                ) : (
                  <>
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-black/20 text-amber-200 group-hover:scale-110 transition-transform">
                      <Sparkles className="h-4 w-4 fill-amber-300 text-amber-200 animate-pulse" />
                    </div>
                    <div className="flex flex-col items-start text-left">
                      <div className="flex items-center gap-1.5">
                        <span className="tracking-tight text-sm font-bold">
                          Bulk Dispatch (Copy All {filteredLeads.length > 0 ? filteredLeads.length : 15})
                        </span>
                        <Copy className="h-3.5 w-3.5 opacity-80 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <span className="text-[10px] font-normal text-amber-100/80">
                        Format for Spark LLM & Mark Contacted
                      </span>
                    </div>
                  </>
                )}
              </button>
            </div>

            {/* Control Bar: Search, Channel Filter, and Refresh */}
            <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3 backdrop-blur-sm">
              {/* Search Input */}
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  placeholder={`Filter ${activeTabDef.label} leads by business name, city, or email...`}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950/80 py-2 pl-9 pr-4 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Channel Filter Chips */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
                <Filter className="h-3.5 w-3.5 text-slate-500 shrink-0 ml-1 mr-1" />
                {(['all', 'email', 'linkedin', 'instagram'] as const).map((channel) => (
                  <button
                    key={channel}
                    type="button"
                    onClick={() => setSelectedChannel(channel)}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium capitalize transition-all cursor-pointer ${
                      selectedChannel === channel
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                    }`}
                  >
                    {channel === 'all' ? 'All Channels' : channel}
                  </button>
                ))}
              </div>

              {/* Refresh Current Strategy Batch Button */}
              <button
                type="button"
                onClick={handleRefreshCurrentTab}
                disabled={isPending}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white transition-all cursor-pointer shrink-0 disabled:opacity-60"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isPending ? 'animate-spin text-indigo-400' : ''}`} />
                <span>{isPending ? 'Refreshing...' : `Refresh ${activeTabDef.label}`}</span>
              </button>
            </div>

            {/* Main Responsive Grid of up to 15 Strategy Leads */}
            {isPending ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/40 p-16 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
                <p className="mt-3 text-xs text-slate-400">Loading {activeTabDef.label} batch from PostgreSQL...</p>
              </div>
            ) : filteredLeads.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {filteredLeads.map((lead, idx) => (
                  <LeadCard
                    key={lead.id}
                    lead={lead}
                    index={idx}
                    onContacted={handleLeadContacted}
                  />
                ))}
              </div>
            ) : currentLeads.length === 0 ? (
              /* Empty State: All Leads in this Strategy Contacted or None Pending */
              <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-400 shadow-inner">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h3 className="mt-4 text-lg font-semibold text-white">
                  No Pending Leads in {activeTabDef.label}
                </h3>
                <p className="mt-1 max-w-md text-xs text-slate-400 leading-relaxed">
                  All leads in this category have been dispatched and marked as contacted in PostgreSQL,
                  or no leads matching this campaign strategy were found. Run the Python pipeline or select
                  another strategy tab above.
                </p>
                <button
                  type="button"
                  onClick={handleRefreshCurrentTab}
                  disabled={isPending}
                  className="mt-5 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-lg hover:bg-indigo-500 transition-all cursor-pointer"
                >
                  <RefreshCw className={`h-4 w-4 ${isPending ? 'animate-spin' : ''}`} />
                  <span>Check for New Pending Leads</span>
                </button>
              </div>
            ) : (
              /* Filter Empty State */
              <div className="flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center">
                <p className="text-xs text-slate-400">
                  No leads match your current search or channel filter in {activeTabDef.label}.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setSearchTerm('');
                    setSelectedChannel('all');
                  }}
                  className="mt-2 text-xs font-medium text-indigo-400 hover:text-indigo-300 cursor-pointer"
                >
                  Clear search & filters
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
