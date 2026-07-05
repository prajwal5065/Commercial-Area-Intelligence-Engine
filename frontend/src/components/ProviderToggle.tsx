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
}

/**
 * Manual LLM provider picker (Groq / Gemini / OpenAI), shown alongside a
 * stage's StageConfigurator for agents that support choosing which model
 * runs their LLM call. If the chosen provider's API key isn't set on the
 * backend, that agent's call_llm()/call_groq() falls back to Groq with a
 * warning rather than failing - this toggle doesn't need to know which
 * keys are actually configured.
 */
export function ProviderToggle({ value, onChange, disabled }: ProviderToggleProps) {
  return (
    <div>
      <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
        LLM Provider
      </label>
      <div className="flex items-center rounded-lg bg-ink-850 border border-ink-700 p-0.5 w-fit">
        {PROVIDERS.map((p) => (
          <button
            key={p}
            type="button"
            disabled={disabled}
            onClick={() => onChange(p)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors disabled:opacity-40 ${
              value === p
                ? "bg-signal-500 text-ink-950"
                : "text-ink-400 hover:text-ink-200"
            }`}
          >
            {p}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-ink-500 mt-1.5">
        Requires {API_KEY_HINT[value]} set on the backend. Falls back to Groq if missing.
      </p>
    </div>
  );
}
