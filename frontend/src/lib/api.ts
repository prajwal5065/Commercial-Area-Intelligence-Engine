const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type AgentStatus = "Pending" | "Running" | "Done" | "Error";

export interface SessionStatus {
  session_id: string;
  running: boolean;
  error: string | null;
  agent_status: Record<string, AgentStatus>;
  output_file: string | null;
}

export interface CompanyRow {
  company_name?: string;
  category?: string;
  priority?: string;
  subarea_name?: string;
  zone_name?: string;
  city_name?: string;
  country_name?: string;
  [key: string]: unknown;
}

export interface ExplorerOptions {
  countries: string[];
  cities: string[];
  zones: string[];
  subareas: string[];
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
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json();
}

/**
 * Matches Master Agent/backend_api.py exactly - a session-based FastAPI
 * backend (POST /sessions creates a session_id, everything else is scoped
 * under /sessions/{id}/...). See that file's docstring for design notes.
 */
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

  runAgent1: (sessionId: string, topN: number | null) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/1/run`, {
      method: "POST",
      body: JSON.stringify({ top_n: topN }),
    }),

  runAgent2: (sessionId: string, selectedCountries: string[]) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/2/run`, {
      method: "POST",
      body: JSON.stringify({ selected_countries: selectedCountries }),
    }),

  runAgent3: (sessionId: string, selectedCities: string[]) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/3/run`, {
      method: "POST",
      body: JSON.stringify({ selected_cities: selectedCities }),
    }),

  runAgent4: (sessionId: string, selectedZones: string[]) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/4/run`, {
      method: "POST",
      body: JSON.stringify({ selected_zones: selectedZones }),
    }),

  runAgent5: (sessionId: string) =>
    req<{ status: string }>(`/sessions/${sessionId}/agents/5/run`, { method: "POST" }),

  getCountries: (sessionId: string) =>
    req<{ country_name?: string; gdp_rank?: number }[]>(
      `/sessions/${sessionId}/data/countries`
    ),

  getCities: (sessionId: string) =>
    req<{ city?: string; country?: string; tier?: number }[]>(
      `/sessions/${sessionId}/data/cities`
    ),

  getZones: (sessionId: string) =>
    req<{ country: string; city: string; zone_name: string }[]>(
      `/sessions/${sessionId}/data/zones`
    ),

  getSubareas: (sessionId: string) =>
    req<Record<string, unknown>[]>(`/sessions/${sessionId}/data/subareas`),

  getCompanies: (
    sessionId: string,
    filters: { country?: string; city?: string; zone?: string; subarea?: string }
  ) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    return req<CompanyRow[]>(`/sessions/${sessionId}/data/companies?${params.toString()}`);
  },

  getExplorerOptions: (
    sessionId: string,
    filters: { country?: string; city?: string; zone?: string }
  ) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    return req<ExplorerOptions>(
      `/sessions/${sessionId}/data/explorer-options?${params.toString()}`
    );
  },

  downloadUrl: (sessionId: string) => `${BASE_URL}/sessions/${sessionId}/download`,
};
