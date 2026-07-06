import { AlertTriangle } from "lucide-react";
import type { LlmProvider } from "../lib/api";

const PROVIDERS: LlmProvider[] = ["groq", "gemini", "openai"];

const API_KEY_HINT: Record<LlmProvider, string> = {
  groq: "GROQ_API_KEY",
  gemini: "GEMINI_API_KEY",
  openai: "OPENAI_API_KEY",
};

interface ProviderToggleProps {
  value: LlmProvider;
  onChange: (p: LlmProvider) => void;
  disabled?: boolean;
  /** Providers that have hit a rate limit this session (from
   * SessionStatus.rate_limited_providers) - shows a small warning triangle
   * on the corresponding button so the user can see at a glance which
   * option is currently unavailable, before picking it. */
  rateLimited?: string[];
}

/**
 * Manual LLM provider picker (Groq / Gemini / OpenAI), shown alongside a
 * stage's StageConfigurator for agents that support choosing which model
 * runs their LLM call. If the chosen provider's API key isn't set on the
 * backend, that agent's call_llm()/call_groq() falls back to Groq with a
 * warning rather than failing - this toggle doesn't need to know which
 * keys are actually configured.
 */
export function ProviderToggle({ value, onChange, disabled, rateLimited = [] }: ProviderToggleProps) {
  const isLimited = (p: LlmProvider) => rateLimited.includes(p);

  return (
    <div>
      <label className="block font-mono text-[11px] font-semibold tracking-[2.52px] uppercase text-body mb-1.5">
        LLM Provider
      </label>
      <div className="flex items-center rounded-sm bg-canvas border border-hairline p-0.5 w-fit">
        {PROVIDERS.map((p) => (
          <button
            key={p}
            type="button"
            disabled={disabled}
            onClick={() => onChange(p)}
            title={isLimited(p) ? `${p} hit a rate limit this session` : undefined}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-medium capitalize transition-colors disabled:opacity-40 ${
              value === p
                ? "bg-primary text-on-primary"
                : "text-body-mid hover:text-ink"
            }`}
          >
            {isLimited(p) && (
              <AlertTriangle
                className={`w-3 h-3 shrink-0 ${value === p ? "text-on-primary" : "text-amber-400"}`}
              />
            )}
            {p}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-body-mid mt-1.5">
        Requires {API_KEY_HINT[value]} set on the backend. Falls back to Groq if missing.
        {isLimited(value) && (
          <span className="text-amber-400 font-medium"> This provider hit a rate limit this session.</span>
        )}
      </p>
    </div>
  );
}
