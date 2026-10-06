'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  getDailyUsage,
  getPipelineStatus,
  getRunSuggestions,
  startPipelineRun,
  stopPipelineRun,
} from '@/app/runActions';
import type { RunStatus } from '@/lib/pipelineRunner';
import type { DailyUsage } from '@/app/runActions';
import { Play, Shuffle, Square, Loader2, MapPin, Briefcase, CheckCircle2, AlertCircle, Terminal } from 'lucide-react';

interface RunPanelProps {
  onRunFinished: () => void;
}

const POLL_MS = 2000;

export default function RunPanel({ onRunFinished }: RunPanelProps) {
  const [city, setCity] = useState('');
  const [niche, setNiche] = useState('');
  const [quota, setQuota] = useState(15);
  const [suggestions, setSuggestions] = useState<{ cities: string[]; niches: string[] }>({ cities: [], niches: [] });
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [usage, setUsage] = useState<DailyUsage | null>(null);

  const refreshUsage = () => getDailyUsage().then(setUsage).catch(() => {});
  const wasRunning = useRef(false);
  const logRef = useRef<HTMLPreElement>(null);

  // Suggestions for the inputs, plus pick up a run that was started before this page loaded
  useEffect(() => {
    getRunSuggestions().then(setSuggestions).catch(() => {});
    refreshUsage();
    getPipelineStatus().then((s) => {
      setStatus(s);
      wasRunning.current = s.running;
    });
  }, []);

  const running = status?.running ?? false;

  // Poll while a run is in progress; refresh the leads once it ends
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const next = await getPipelineStatus();
      setStatus(next);
      if (wasRunning.current && !next.running) {
        onRunFinished();
        refreshUsage();
      }
      wasRunning.current = next.running;
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running, onRunFinished]);

  useEffect(() => {
    if (showLog && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status?.logLines, showLog]);

  const start = async (mode: 'target' | 'random') => {
    setError(null);
    setIsStarting(true);
    const res = await startPipelineRun({ mode, city, niche, quota: Math.min(quota, maxQuota) });
    setIsStarting(false);
    if (!res.ok || !res.status) {
      setError(res.error || 'Could not start the pipeline.');
      return;
    }
    wasRunning.current = true;
    setStatus(res.status);
  };

  const request = status?.request;
  const capReached = usage?.left === 0;
  const maxQuota = Math.min(100, usage?.left ?? 100);
  const runQuota = status?.effectiveQuota ?? request?.quota ?? 0;
  const lastLine = status?.logLines[status.logLines.length - 1];
  const ended = !!status && !status.running && !!status.finishedAt;
  const stopped = ended && status.stoppedByUser;
  const failed = ended && !status.completed && !status.stoppedByUser;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-white">Find new leads</h2>
          <p className="text-xs text-slate-400">
            Type any city and business type, or hit Random. With Random, a field you fill in stays fixed and blank ones are shuffled.
          </p>
        </div>
        {usage && (
          <span
            className={`rounded-md border px-2.5 py-1 text-xs ${
              capReached
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-slate-700 bg-slate-800/60 text-slate-300'
            }`}
            title="New leads saved today across all runs (DAILY_LEAD_CAP in .env)"
          >
            Today: {usage.today}
            {usage.cap > 0 ? ` / ${usage.cap}` : ''} leads
            {capReached ? ' · daily cap reached' : usage.left != null ? ` · ${usage.left} left` : ''}
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_110px_auto]">
        <label className="relative block">
          <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            list="run-cities"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="City, e.g. Boise or Manchester"
            maxLength={80}
            disabled={running}
            className="w-full rounded-lg border border-slate-800 bg-slate-950/60 py-2 pl-9 pr-3 text-sm text-white placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
          />
          <datalist id="run-cities">
            {suggestions.cities.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>

        <label className="relative block">
          <Briefcase className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            list="run-niches"
            value={niche}
            onChange={(e) => setNiche(e.target.value)}
            placeholder="Niche, e.g. dentist or roofing"
            maxLength={80}
            disabled={running}
            className="w-full rounded-lg border border-slate-800 bg-slate-950/60 py-2 pl-9 pr-3 text-sm text-white placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
          />
          <datalist id="run-niches">
            {suggestions.niches.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        </label>

        <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 px-3 text-xs text-slate-400">
          Leads
          <input
            type="number"
            min={1}
            max={Math.max(1, maxQuota)}
            value={quota}
            onChange={(e) => setQuota(Number(e.target.value))}
            disabled={running}
            className="w-full bg-transparent py-2 text-sm text-white focus:outline-none disabled:opacity-50"
          />
        </label>

        <div className="flex gap-2">
          {running ? (
            <button
              onClick={() => stopPipelineRun()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-300 hover:bg-rose-500/20"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          ) : (
            <>
              <button
                onClick={() => start('target')}
                disabled={isStarting || capReached || !city.trim() || !niche.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
                title="Find leads for exactly this city and niche"
              >
                {isStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run
              </button>
              <button
                onClick={() => start('random')}
                disabled={isStarting || capReached}
                className="inline-flex items-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-300 hover:bg-violet-500/20 disabled:opacity-40"
                title="Shuffle random cities and niches until the lead count is reached"
              >
                <Shuffle className="h-4 w-4" />
                Random
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-rose-400">
          <AlertCircle className="h-3.5 w-3.5" />
          {error}
        </p>
      )}

      {status?.startedAt && request && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 text-slate-300">
              {running ? (
                <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
              ) : failed || stopped ? (
                <AlertCircle className={`h-4 w-4 ${failed ? 'text-rose-400' : 'text-amber-400'}`} />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              )}
              <span>
                {running ? 'Running' : failed ? 'Failed' : stopped ? 'Stopped' : 'Finished'}
                {' · '}
                {request.mode === 'random' ? 'Random' : 'Target'}
                {status.currentTarget && (
                  <>
                    {' · '}
                    <span className="text-white">{status.currentTarget.niche}</span> in{' '}
                    <span className="text-white">{status.currentTarget.city}</span>
                  </>
                )}
              </span>
            </div>
            <span className="font-semibold text-white">
              {status.inserted} / {runQuota} new leads
            </span>
          </div>

          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
              style={{ width: `${Math.min(100, (status.inserted / Math.max(1, runQuota)) * 100)}%` }}
            />
          </div>

          {lastLine && !showLog && <p className="mt-2 truncate font-mono text-[11px] text-slate-500">{lastLine}</p>}
          {failed && (status.errorLines?.length ?? 0) > 0 && (
            <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-md border border-rose-500/30 bg-rose-950/30 p-2 font-mono text-[11px] text-rose-300">
              {status.errorLines.join('\n')}
            </pre>
          )}
          {ended && status.completed && status.effectiveQuota === 0 && (
            <p className="mt-2 text-xs text-amber-300/80">
              Daily cap already reached, so nothing was scraped. Raise DAILY_LEAD_CAP in .env to allow more.
            </p>
          )}
          {ended && !failed && !stopped && runQuota > 0 && status.inserted < runQuota && (
            <p className="mt-2 text-xs text-amber-300/80">
              Ran out of new businesses before reaching {runQuota}. Try another city or niche, or Random.
            </p>
          )}

          <button
            onClick={() => setShowLog((v) => !v)}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200"
          >
            <Terminal className="h-3 w-3" />
            {showLog ? 'Hide log' : 'Show log'}
          </button>
          {showLog && (
            <pre
              ref={logRef}
              className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-black/40 p-2 font-mono text-[11px] leading-relaxed text-slate-400"
            >
              {status.logLines.join('\n') || 'Waiting for output...'}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
