import React from 'react';
import { Target, Database, Activity, Sparkles } from 'lucide-react';

export default function Header() {
  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-40">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo / Brand */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 via-violet-600 to-amber-500 shadow-md shadow-indigo-500/20">
              <Target className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold tracking-tight text-white sm:text-base">
                  B2B Lead Command Center
                </h1>
                <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold text-indigo-400 border border-indigo-500/20">
                  Daily 15 FIFO
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Playwright & Ollama Acquisition Pipeline • Gemini Spark Dispatch
              </p>
            </div>
          </div>

          {/* System Status Indicators */}
          <div className="flex items-center gap-4">
            {/* Database Live Status */}
            <div className="hidden sm:flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300">
              <Database className="h-3.5 w-3.5 text-indigo-400" />
              <span>PostgreSQL:</span>
              <span className="flex items-center gap-1 text-emerald-400 font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Connected
              </span>
            </div>

            {/* Target Quota Tag */}
            <div className="flex items-center gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300 font-medium">
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
              <span>Quota: 15 / Day</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
