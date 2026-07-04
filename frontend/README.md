# Commercial Area Intelligence Engine — Frontend

React + TypeScript + Vite + Tailwind 4 frontend, replacing the Streamlit UI
(`Master Agent/Exp_Full_Dash.py`). Talks to the FastAPI backend at
`Master Agent/backend_api.py`.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_URL if the backend isn't on localhost:8000
npm run dev
```

Requires the backend running first:

```bash
cd "Master Agent"
pip install fastapi "uvicorn[standard]"
uvicorn backend_api:app --reload --port 8000
```

(Run from inside `Master Agent/` so `run_pipeline`'s path setup resolves the
same way it does under Streamlit.)

## How it maps to the backend

`backend_api.py` is session-based: `POST /sessions` returns a `session_id`,
and every other call is scoped under `/sessions/{id}/...`. This frontend
creates one session on load and polls `/sessions/{id}/status` — the direct
replacement for the original app's `st.rerun()` loop while a background
thread runs a pipeline phase.

| UI action | Backend call |
|---|---|
| Run Agent N | `POST /sessions/{id}/agents/N/run` |
| Status polling | `GET /sessions/{id}/status` |
| Reset pipeline | `DELETE /sessions/{id}` |
| Data explorer dropdowns | `GET /sessions/{id}/data/explorer-options` |
| Results table | `GET /sessions/{id}/data/companies` |
| Download results | `GET /sessions/{id}/download` |

## Design decisions

- **Palette**: deep ink (`#0B0F17`) base rather than pure black, with a single
  amber signal color (`#F5A623`) for "running" state — deliberately not the
  default blue/green pairing most generated dashboards reach for.
- **Type**: JetBrains Mono for anything numeric/status-related (this is an
  instrument panel reading pipeline telemetry), Inter for labels and prose.
- **Signature element**: the left-hand `PipelineRail` encodes the actual
  dependency chain of the 5 agents (Agent 2 can't run until Agent 1 is done,
  etc.) — a real sequence from the domain, not a decorative numbered list.
- Every interactive element has a visible focus ring; `prefers-reduced-motion`
  is respected globally.

## Structure

```
src/
├── components/
│   ├── PipelineRail.tsx    # signature nav element, agent sequence + status
│   ├── ResultsTable.tsx    # scraped company results
│   └── ui.tsx              # Card, Button, Select, StatChip, EmptyState
├── pages/
│   ├── Dashboard.tsx       # execute pipeline + data explorer + results
│   └── AgentDetail.tsx     # raw per-agent table view
├── hooks/usePipelineSession.ts  # session creation + status polling
└── lib/api.ts              # typed fetch client matching backend_api.py exactly
```

## Known limitations

- Not tested against a live backend + Supabase + Groq + Playwright stack — no
  credentials or network access to those services in the environment this was
  built in. Build and type-checking are verified (`npm run build`,
  `tsc --noEmit`); the actual data flow depends on `backend_api.py`'s
  underlying pipeline calls succeeding.
- No auth — matches the original app's single-user, single-session-per-tab
  assumption.
