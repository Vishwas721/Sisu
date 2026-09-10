'use client';

import React, { useState } from 'react';
import { Lead } from '@/lib/db';
import { markLeadContacted } from '@/app/actions';
import {
  Building2,
  MapPin,
  Globe,
  Mail,
  Sparkles,
  Copy,
  CheckCircle2,
  ExternalLink,
  Bot,
  AlertCircle,
  Wrench,
  Cpu,
  Share2,
} from 'lucide-react';

interface LeadCardProps {
  lead: Lead;
  index: number;
  onContacted: (id: number, businessName: string) => void;
}

// Clean custom SVG icons for LinkedIn and Instagram
function LinkedinIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="24"
      height="24"
      stroke="currentColor"
      strokeWidth="2"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect width="4" height="12" x="2" y="9" />
      <circle cx="4" cy="4" r="2" />
    </svg>
  );
}

function InstagramIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="24"
      height="24"
      stroke="currentColor"
      strokeWidth="2"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

export default function LeadCard({ lead, index, onContacted }: LeadCardProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [copiedOnlyMessage, setCopiedOnlyMessage] = useState(false);
  const [statusState, setStatusState] = useState<'idle' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const strategy = lead.campaign_strategy || 'legacy_redesign';

  /**
   * Format complete lead dossier for Gemini Spark clipboard dispatch
   */
  const formatSparkClipboardPayload = (): string => {
    return [
      `Target Business: ${lead.business_name}`,
      `City: ${lead.city || 'N/A'}`,
      `Strategy Angle: ${strategy}`,
      `Website: ${lead.website_url || 'None (Social Media Only)'}`,
      `Contact Channels:`,
      `  • Email: ${lead.email || 'None discovered'}`,
      `  • Instagram: ${lead.instagram_url || 'None discovered'}`,
      `  • LinkedIn: ${lead.linkedin_url || 'None discovered'}`,
      ``,
      `--- AI Outreach Draft (${strategy}) ---`,
      lead.ai_drafted_message || 'No drafted message available.',
    ].join('\n');
  };

  /**
   * Spark Dispatch Action:
   * 1. Instantly copy contact dossier & AI message to clipboard
   * 2. Trigger Server Action to UPDATE database status to 'contacted'
   * 3. Optimistically remove card from active grid
   */
  const handleSparkDispatch = async () => {
    if (isProcessing || statusState === 'success') return;
    setIsProcessing(true);
    setErrorMessage(null);

    const payload = formatSparkClipboardPayload();

    try {
      // 1. Copy to clipboard
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(payload);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = payload;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }

      // 2. Set optimistic visual state
      setStatusState('success');

      // 3. Trigger Next.js Server Action
      const res = await markLeadContacted(lead.id);
      if (!res.success) {
        throw new Error(res.message || 'Server action failed to update lead in database.');
      }

      // 4. Optimistically remove card from parent grid after smooth visual transition
      setTimeout(() => {
        onContacted(lead.id, lead.business_name);
      }, 400);
    } catch (err: unknown) {
      console.error('Spark dispatch error:', err);
      setStatusState('error');
      setErrorMessage((err as Error).message || 'Failed to dispatch lead.');
      setIsProcessing(false);
    }
  };

  /**
   * Helper to copy only the AI message text
   */
  const handleCopyMessageOnly = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!lead.ai_drafted_message) return;
    try {
      await navigator.clipboard.writeText(lead.ai_drafted_message);
      setCopiedOnlyMessage(true);
      setTimeout(() => setCopiedOnlyMessage(false), 2000);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  };

  // Determine if website is a dedicated website vs a social profile URL
  const isSocialWebsite =
    lead.website_url &&
    (lead.website_url.includes('instagram.com') ||
      lead.website_url.includes('facebook.com') ||
      strategy === 'no_website');

  return (
    <div
      className={`group relative flex flex-col justify-between rounded-xl border bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm transition-all duration-300 hover:border-indigo-500/50 hover:shadow-indigo-500/10 ${
        statusState === 'success'
          ? 'scale-95 opacity-20 border-emerald-500/50 bg-emerald-950/20 translate-y-2 pointer-events-none'
          : 'border-slate-800'
      }`}
    >
      <div>
        {/* Top Meta Bar: Index, Strategy Pill, and City */}
        <div className="flex items-start justify-between gap-2 border-b border-slate-800/80 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500/20 text-xs font-bold text-indigo-400">
              #{index + 1}
            </span>

            {/* Campaign Strategy Colored Pill/Badge */}
            {strategy === 'no_website' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-fuchsia-500/10 px-2.5 py-0.5 text-xs font-semibold text-fuchsia-400 border border-fuchsia-500/25">
                <Share2 className="h-3 w-3" />
                No Website
              </span>
            )}
            {strategy === 'legacy_redesign' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-400 border border-amber-500/25">
                <Wrench className="h-3 w-3" />
                Legacy Redesign
              </span>
            )}
            {strategy === 'ai_automation' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-500/25">
                <Cpu className="h-3 w-3" />
                AI Automation
              </span>
            )}
          </div>

          {lead.city && (
            <span className="flex items-center gap-1 text-xs text-slate-400 shrink-0">
              <MapPin className="h-3.5 w-3.5 text-rose-400" />
              {lead.city}
            </span>
          )}
        </div>

        {/* Business Title & Domain / Presence */}
        <div className="mt-3">
          <h3 className="text-lg font-semibold tracking-tight text-white group-hover:text-indigo-300 transition-colors flex items-center gap-1.5">
            <Building2 className="h-4 w-4 text-indigo-400 shrink-0" />
            <span className="truncate">{lead.business_name}</span>
          </h3>

          {lead.website_url && !isSocialWebsite ? (
            <a
              href={lead.website_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-mono text-slate-400 hover:text-indigo-400 transition-colors"
            >
              <Globe className="h-3 w-3 text-slate-500 shrink-0" />
              <span className="truncate max-w-[240px]">{lead.website_url.replace(/^https?:\/\//, '')}</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-60" />
            </a>
          ) : isSocialWebsite ? (
            <a
              href={lead.website_url || lead.instagram_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-mono text-fuchsia-400/90 hover:text-fuchsia-300 transition-colors"
            >
              <Share2 className="h-3 w-3 text-fuchsia-500 shrink-0" />
              <span className="truncate max-w-[240px]">Social Profile Presence Only</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-60" />
            </a>
          ) : (
            <span className="mt-1 inline-flex items-center gap-1 text-xs font-mono text-slate-500">
              <Globe className="h-3 w-3 opacity-40" />
              <span>No active website URL</span>
            </span>
          )}
        </div>

        {/* Available Contact Channels */}
        <div className="mt-4 flex flex-wrap gap-2">
          {/* Email Badge */}
          {lead.email ? (
            <a
              href={`mailto:${lead.email}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
              title={lead.email}
            >
              <Mail className="h-3 w-3 shrink-0" />
              <span className="truncate max-w-[140px]">{lead.email}</span>
            </a>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/40 px-2 py-1 text-xs text-slate-500 border border-slate-800">
              <Mail className="h-3 w-3 opacity-40" />
              <span>No email</span>
            </span>
          )}

          {/* LinkedIn Badge */}
          {lead.linkedin_url ? (
            <a
              href={lead.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
              title="View LinkedIn Profile"
            >
              <LinkedinIcon className="h-3 w-3 shrink-0" />
              <span>LinkedIn</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-70" />
            </a>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/40 px-2 py-1 text-xs text-slate-500 border border-slate-800">
              <LinkedinIcon className="h-3 w-3 opacity-40" />
              <span>No LinkedIn</span>
            </span>
          )}

          {/* Instagram Badge */}
          {lead.instagram_url ? (
            <a
              href={lead.instagram_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-fuchsia-500/10 px-2.5 py-1 text-xs font-medium text-fuchsia-400 border border-fuchsia-500/20 hover:bg-fuchsia-500/20 transition-colors"
              title="View Instagram Profile"
            >
              <InstagramIcon className="h-3 w-3 shrink-0" />
              <span>Instagram</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-70" />
            </a>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/40 px-2 py-1 text-xs text-slate-500 border border-slate-800">
              <InstagramIcon className="h-3 w-3 opacity-40" />
              <span>No IG</span>
            </span>
          )}
        </div>

        {/* AI Drafted Outreach Message Section */}
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
          <div className="flex items-center justify-between pb-2 border-b border-slate-900">
            <div className="flex items-center gap-1.5 text-xs font-medium text-indigo-400">
              <Bot className="h-3.5 w-3.5 text-indigo-400" />
              <span className="capitalize">{strategy.replace('_', ' ')} Pitch</span>
            </div>

            {lead.ai_drafted_message && (
              <button
                type="button"
                onClick={handleCopyMessageOnly}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-white transition-colors cursor-pointer"
                title="Copy message only"
              >
                {copiedOnlyMessage ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    <span className="text-emerald-400 font-medium">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    <span>Copy Text</span>
                  </>
                )}
              </button>
            )}
          </div>

          <p className="mt-2 text-xs leading-relaxed text-slate-300 italic line-clamp-4 hover:line-clamp-none transition-all">
            {lead.ai_drafted_message
              ? `"${lead.ai_drafted_message}"`
              : 'No AI message generated for this lead.'}
          </p>
        </div>
      </div>

      {/* Error Alert if any */}
      {errorMessage && (
        <div className="mt-3 flex items-center gap-1.5 rounded-md bg-rose-500/10 p-2 text-xs text-rose-400 border border-rose-500/20">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Primary "Spark Dispatch" Action Button */}
      <div className="mt-5 pt-3 border-t border-slate-800/80">
        <button
          type="button"
          onClick={handleSparkDispatch}
          disabled={isProcessing || statusState === 'success'}
          className={`w-full flex items-center justify-center gap-2 rounded-lg py-2.5 px-4 text-xs font-semibold shadow-md transition-all duration-200 cursor-pointer ${
            statusState === 'success'
              ? 'bg-emerald-600 text-white cursor-default'
              : 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] hover:shadow-indigo-500/25'
          } ${isProcessing ? 'opacity-70 cursor-wait' : ''}`}
        >
          {statusState === 'success' ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-white animate-bounce" />
              <span>Copied & Marked Contacted!</span>
            </>
          ) : isProcessing ? (
            <>
              <Sparkles className="h-4 w-4 animate-spin text-indigo-200" />
              <span>Dispatching to Spark...</span>
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4 text-amber-300" />
              <Copy className="h-3.5 w-3.5" />
              <span>Copy & Mark Contacted</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
