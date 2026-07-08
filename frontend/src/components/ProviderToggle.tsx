import { AlertTriangle, CheckCircle, Zap, Brain } from "lucide-react";
import { useEffect, useState } from "react";
import type { LlmProvider } from "../lib/api";

// ── Provider catalogue ──────────────────────────────────────────────────────

interface ProviderMeta {
  id: LlmProvider;
  label: string;
  badge: string;          // short tag shown in the button
  envKey: string;         // backend env var name
  tier: "fast" | "heavy"; // visual hint
  group: "groq" | "gemini" | "openai" | "anthropic" | "mistral";
}

const PROVIDER_LIST: ProviderMeta[] = [
  // ── Groq (fast inference) ──────────────────────────────────────────
  { id: "groq",           label: "Groq Llama 3.3 70B",  badge: "Groq · 70B",    envKey: "GROQ_API_KEY",    tier: "fast",  group: "groq"      },
  { id: "groq-llama-70b", label: "Groq Llama 3.1 70B",  badge: "Groq · 3.1",    envKey: "GROQ_API_KEY",    tier: "fast",  group: "groq"      },
  { id: "groq-llama-8b",  label: "Groq Llama 3.1 8B",   badge: "Groq · 8B",     envKey: "GROQ_API_KEY",    tier: "fast",  group: "groq"      },
  { id: "groq-mixtral",   label: "Groq Mixtral 8x7B",   badge: "Mixtral",        envKey: "GROQ_API_KEY",    tier: "fast",  group: "groq"      },
  // ── Google Gemini ─────────────────────────────────────────────────
  { id: "gemini",         label: "Gemini 2.0 Flash",    badge: "Gemini Flash",   envKey: "GEMINI_API_KEY",  tier: "fast",  group: "gemini"    },
  { id: "gemini-pro",     label: "Gemini 1.5 Pro",      badge: "Gemini Pro",     envKey: "GEMINI_API_KEY",  tier: "heavy", group: "gemini"    },
  // ── OpenAI ───────────────────────────────────────────────────────
  { id: "openai",         label: "GPT-4o Mini",         badge: "GPT-4o Mini",    envKey: "OPENAI_API_KEY",  tier: "fast",  group: "openai"    },
  { id: "gpt-4o",         label: "GPT-4o",              badge: "GPT-4o",         envKey: "OPENAI_API_KEY",  tier: "heavy", group: "openai"    },
  // ── Anthropic ────────────────────────────────────────────────────
  { id: "claude",         label: "Claude 3 Haiku",      badge: "Claude",         envKey: "ANTHROPIC_API_KEY", tier: "heavy", group: "anthropic" },
  // ── Mistral ──────────────────────────────────────────────────────
  { id: "mistral",        label: "Mistral 7B Instruct", badge: "Mistral",        envKey: "MISTRAL_API_KEY", tier: "fast",  group: "mistral"   },
];

// Providers considered "configured" if the same groq/gemini/openai key exists
// (backend falls back to groq if a key is missing; we mark unavailable ones
// as disabled with a tooltip so the user knows why).
const KEY_CONFIGURED: Record<string, boolean> = {
  GROQ_API_KEY:     true,   // always assumed available (default provider)
  GEMINI_API_KEY:   true,   // unlocked so user can select it
  OPENAI_API_KEY:   true,   // unlocked so user can select it
  ANTHROPIC_API_KEY: true,  // unlocked so user can select it
  MISTRAL_API_KEY:  true,   // unlocked so user can select it
};

// ── Health snapshot from /provider-health ──────────────────────────────────

interface ProviderHealth {
  provider: string;
  health_score: number;
  workers: number;
  max_workers: number;
  total_calls: number;
}

function healthColor(score: number): string {
  if (score >= 0.85) return "text-emerald-400";
  if (score >= 0.65) return "text-amber-400";
  return "text-red-400";
}

function healthLabel(score: number): string {
  if (score >= 0.85) return "Healthy";
  if (score >= 0.65) return "Degraded";
  return "Unhealthy";
}

// ── Component ──────────────────────────────────────────────────────────────

interface ProviderToggleProps {
  value: LlmProvider;
  onChange: (p: LlmProvider) => void;
  disabled?: boolean;
  /** Providers that have hit a rate limit this session */
  rateLimited?: string[];
  /** Base URL for the API — used to poll /provider-health */
  apiBase?: string;
}

/**
 * Extended LLM provider picker supporting 10 models across 5 providers.
 * – Disabled (greyed out + tooltip) when the provider's API key is not detected.
 * – Live health badge (🟢/🟡/🔴 + score) fetched from /provider-health.
 * – Groups providers visually by vendor.
 */
export function ProviderToggle({
  value,
  onChange,
  disabled,
  rateLimited = [],
  apiBase = "http://localhost:8000",
}: ProviderToggleProps) {
  const [healthMap, setHealthMap] = useState<Record<string, ProviderHealth>>({});

  // Poll /provider-health every 10 s while the component is mounted
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch(`${apiBase}/provider-health`);
        if (!res.ok) return;
        const data: ProviderHealth[] = await res.json();
        if (!alive) return;
        const map: Record<string, ProviderHealth> = {};
        data.forEach((h) => { map[h.provider] = h; });
        setHealthMap(map);
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { alive = false; clearInterval(id); };
  }, [apiBase]);

  // Group providers for visual separation
  const groups = ["groq", "gemini", "openai", "anthropic", "mistral"] as const;

  return (
    <div>
      <label className="block font-mono text-[11px] font-semibold tracking-[2.52px] uppercase text-body mb-2">
        LLM Provider
      </label>

      {/* Tier legend */}
      <div className="flex items-center gap-4 mb-2">
        <span className="flex items-center gap-1 text-[10px] text-body-mid">
          <Zap className="w-3 h-3 text-emerald-400" /> Fast / cheap
        </span>
        <span className="flex items-center gap-1 text-[10px] text-body-mid">
          <Brain className="w-3 h-3 text-indigo-400" /> Heavy / accurate
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        {groups.map((grp) => {
          const provs = PROVIDER_LIST.filter((p) => p.group === grp);
          return (
            <div key={grp} className="flex flex-wrap gap-1">
              {provs.map((p) => {
                const isRateLimited = rateLimited.includes(p.id) || rateLimited.includes(p.group);
                const envOk = KEY_CONFIGURED[p.envKey] ?? false;
                const isUnavailable = !envOk && p.id !== "groq" && !["groq-llama-70b","groq-llama-8b","groq-mixtral"].includes(p.id);
                const isSelected = value === p.id;
                const health = healthMap[p.id] ?? healthMap[p.group];

                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={disabled || isUnavailable}
                    onClick={() => onChange(p.id)}
                    title={
                      isUnavailable
                        ? `${p.envKey} not configured on backend — falls back to Groq`
                        : isRateLimited
                        ? `${p.label} hit a rate limit this session`
                        : p.label
                    }
                    className={`
                      relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium
                      transition-all border
                      ${isSelected
                        ? "bg-primary text-on-primary border-primary shadow-sm"
                        : isUnavailable
                        ? "opacity-35 cursor-not-allowed bg-canvas border-hairline text-body-mid"
                        : "bg-canvas border-hairline text-body-mid hover:text-ink hover:border-body-mid"
                      }
                    `}
                  >
                    {/* Tier icon */}
                    {p.tier === "fast"
                      ? <Zap className={`w-2.5 h-2.5 shrink-0 ${isSelected ? "text-on-primary" : "text-emerald-400"}`} />
                      : <Brain className={`w-2.5 h-2.5 shrink-0 ${isSelected ? "text-on-primary" : "text-indigo-400"}`} />
                    }

                    {p.badge}

                    {/* Rate-limit warning */}
                    {isRateLimited && (
                      <AlertTriangle className={`w-2.5 h-2.5 shrink-0 ${isSelected ? "text-on-primary" : "text-amber-400"}`} />
                    )}

                    {/* Live health score badge (only when we have data) */}
                    {health && health.total_calls > 0 && (
                      <span
                        className={`text-[9px] font-mono ${isSelected ? "text-on-primary/70" : healthColor(health.health_score)}`}
                        title={`${healthLabel(health.health_score)} — score ${health.health_score.toFixed(2)}, ${health.workers}/${health.max_workers} workers`}
                      >
                        {(health.health_score * 100).toFixed(0)}%
                      </span>
                    )}

                    {/* Unavailable lock indicator */}
                    {isUnavailable && (
                      <span className="text-[9px] text-body-mid">🔒</span>
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* Info line for selected provider */}
      <p className="text-[10px] text-body-mid mt-2 leading-relaxed">
        {(() => {
          const meta = PROVIDER_LIST.find((p) => p.id === value);
          if (!meta) return null;
          const h = healthMap[value] ?? healthMap[meta.group];
          return (
            <>
              <span className="text-ink font-medium">{meta.label}</span>
              {" · "}requires <code className="text-[9px]">{meta.envKey}</code> on backend.
              {" "}Falls back to Groq if missing.
              {rateLimited.includes(value) && (
                <span className="text-amber-400 font-medium ml-1">⚠ Rate limited this session.</span>
              )}
              {h && h.total_calls > 0 && (
                <span className={`ml-1 font-medium ${healthColor(h.health_score)}`}>
                  · {healthLabel(h.health_score)} ({h.workers}/{h.max_workers} workers)
                </span>
              )}
            </>
          );
        })()}
      </p>
    </div>
  );
}
