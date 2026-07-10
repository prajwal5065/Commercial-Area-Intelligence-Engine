
const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type AgentStatus = "Pending" | "Running" | "Done" | "Error" | "error" | "pending" | "running" | "done" | "failed" | "Failed" | "skipped";

// Manual model choice for agents that support it.
// Matches the PROVIDERS registry in the backend agents.
export type LlmProvider =
  | "groq"
  | "gemini"
  | "openai"
  | "groq-llama-70b"
  | "groq-llama-8b"
  | "groq-mixtral"
  | "gemini-pro"
  | "gpt-4o"
  | "claude"
  | "mistral";


export interface LogEntry {
  ts: string;
  level: "INFO" | "WARN" | "ERROR" | "SUCCESS" | "STAGE" | "METRIC" | "EOF" | "RATE_LIMIT";
  agent: string;
  message: string;
}

export interface AgentDetail {
  agent_id: string;
  agent_name: string;
  status: string;
  elapsed: string;
  start_time: number | null;
  end_time: number | null;
  input_count: number;
  output_count: number;
  error_count: number;
  retry_count: number;
  errors: string[];
  items_out: string[];
  active_instances: number;
}

export interface SessionStatus {
  session_id: string;
  running: boolean;
  error: string | null;
  agent_status: Record<string, AgentStatus>;
  output_file: string | null;
  // Production fields
  pipeline_status: string;
  elapsed: string | null;
  counts: {
    countries: number;
    cities: number;
    zones: number;
    subareas: number;
    companies: number;
    companies_raw: number;
    duplicates_removed: number;
    supabase_inserted: number;
  };
  system: {
    peak_cpu: number;
    peak_mem_mb: number;
    cpu_now: number;
    mem_mb: number;
  };
  failed_agent: string | null;
  agents_detail: Record<string, AgentDetail>;
  // Providers (groq/gemini/openai/tavily) that have hit a rate limit this
  // session. Used to show a warning triangle on the provider toggle.
  rate_limited_providers: string[];
}

export interface PipelineRunRequest {
  top_n?: number | null;
  selected_countries?: string[];
  selected_cities?: string[];
  selected_zones?: string[];
  max_scrolls?: number;
  max_scrapers?: number;
  skip_supabase?: boolean;
  stage2_provider?: string;
  stage3_provider?: string;
  stage4_provider?: string;
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch { /* not json */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req<{ status: string }>("/health"),

  createSession: () =>
    req<{ session_id: string; created_at: string }>("/sessions", { method: "POST" }),

  getStatus: (sessionId: string) =>
    req<SessionStatus>(`/sessions/${sessionId}/status`),

  resetSession: (sessionId: string) =>
    req<{ session_id: string; reset: boolean }>(`/sessions/${sessionId}`, {
      method: "DELETE",
    }),

  // ── Full pipeline ──────────────────────────────────────────────────
  runFullPipeline: (sessionId: string, body: PipelineRunRequest = {}) =>
    req<{ status: string; message: string }>(`/sessions/${sessionId}/pipeline/run`, {
      method: "POST",
      body: JSON.stringify({
        top_n: body.top_n ?? null,
        selected_countries: body.selected_countries ?? [],
        selected_cities: body.selected_cities ?? [],
        selected_zones: body.selected_zones ?? [],
        max_scrolls: body.max_scrolls ?? 8,
        max_scrapers: body.max_scrapers ?? 3,
        skip_supabase: body.skip_supabase ?? false,
      }),
    }),

  stopPipeline: (sessionId: string) =>
    req<{ status: string }>(`/sessions/${sessionId}/pipeline/stop`, { method: "POST" }),

  getLogs: (sessionId: string) =>
    req<LogEntry[]>(`/sessions/${sessionId}/pipeline/logs`),

  // SSE stream URL (not a fetch — use EventSource)
  logsStreamUrl: (sessionId: string) =>
    `${BASE_URL}/sessions/${sessionId}/pipeline/logs/stream`,

  // ── Individual agents (manual mode) ──────────────────────────────
  runAgent1: (sessionId: string, topN: number | null, countries: string[] = []) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/1/run`, {
      method: "POST",
      body: JSON.stringify({ top_n: topN, countries: countries.length ? countries : null }),
    }),
  runAgent2: (sessionId: string, selectedCountries: string[], provider: LlmProvider = "groq") =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/2/run`, {
      method: "POST",
      body: JSON.stringify({ selected_countries: selectedCountries, provider }),
    }),
  runAgent3: (sessionId: string, selectedCities: string[], provider: LlmProvider = "groq") =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/3/run`, {
      method: "POST",
      body: JSON.stringify({ selected_cities: selectedCities, provider }),
    }),
  runAgent4: (sessionId: string, selectedZones: string[], provider: LlmProvider = "groq") =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/4/run`, {
      method: "POST",
      body: JSON.stringify({ selected_zones: selectedZones, provider }),
    }),
  runAgent5: (sessionId: string) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/5/run`, { method: "POST" }),

  // ── Data ──────────────────────────────────────────────────────────
  getCountries: (sessionId: string) =>
    req<{ country_name?: string; gdp_rank?: number }[]>(`/sessions/${sessionId}/data/countries`),

  getCities: (sessionId: string) =>
    req<{ city?: string; country?: string; tier?: number }[]>(`/sessions/${sessionId}/data/cities`),

  getZones: (sessionId: string) =>
    req<{ country: string; city: string; zone_name: string }[]>(`/sessions/${sessionId}/data/zones`),

  getSubareas: (sessionId: string) =>
    req<Record<string, unknown>[]>(`/sessions/${sessionId}/data/subareas`),

  getCompanies: (
    sessionId: string,
    filters: { country?: string; city?: string; zone?: string; subarea?: string }
  ) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    return req<Record<string, unknown>[]>(`/sessions/${sessionId}/data/companies?${params.toString()}`);
  },

  downloadUrl: (sessionId: string) => `${BASE_URL}/sessions/${sessionId}/download`,
};
