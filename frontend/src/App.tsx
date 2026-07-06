import { useState } from "react";
import { usePipelineSession } from "./hooks/usePipelineSession";
import { PipelineRail } from "./components/PipelineRail";
import { Dashboard } from "./pages/Dashboard";
import { AgentDetail } from "./pages/AgentDetail";
import { WifiOff } from "lucide-react";

function App() {
  const { sessionId, status, connectionError, refresh } = usePipelineSession();
  const [activePage, setActivePage] = useState<"dashboard" | string>("dashboard");

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="flex items-center justify-between px-6 py-4 border-b border-canvas-softer bg-canvas-soft">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center font-mono font-bold text-on-primary text-sm">
            CI
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight leading-none" style={{ fontFamily: "var(--font-display)" }}>
              Commercial Area Intelligence Engine
            </h1>
            <p className="text-xs text-body-mid mt-1">
              Automated B2B lead pipeline · country → city → zone → sub-area → leads
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {connectionError ? (
            <span className="flex items-center gap-1.5 font-mono text-xs text-status-error">
              <WifiOff className="w-3.5 h-3.5" />
              Backend unreachable
            </span>
          ) : (
            <span className="flex items-center gap-1.5 font-mono text-xs text-status-done">
              <span className="w-1.5 h-1.5 rounded-full bg-status-done" />
              Connected
            </span>
          )}
        </div>
      </header>

      <div className="flex">
        <aside className="w-64 shrink-0 border-r border-canvas-softer min-h-[calc(100vh-73px)] p-3">
          <button
            onClick={() => setActivePage("dashboard")}
            className={`w-full text-left px-4 py-2.5 rounded-lg text-sm font-medium mb-2 transition-colors ${
              activePage === "dashboard"
                ? "bg-canvas-softer text-ink"
                : "text-body-mid hover:bg-canvas-soft hover:text-ink-mid"
            }`}
          >
            Dashboard
          </button>
          <div className="my-3 border-t border-canvas-softer" />
          <p className="px-4 font-mono text-[10px] uppercase tracking-widest text-body-mid mb-2">
            Pipeline
          </p>
          {status && (
            <PipelineRail
              agentStatus={status.agent_status}
              activeAgent={activePage === "dashboard" ? "" : activePage}
              onSelectAgent={setActivePage}
            />
          )}
        </aside>

        <main className="flex-1 p-6 max-w-[1400px] mx-auto w-full">
          {!sessionId || !status ? (
            <p className="text-sm text-body-mid font-mono">Connecting to pipeline…</p>
          ) : activePage === "dashboard" ? (
            <Dashboard sessionId={sessionId} status={status} refresh={refresh} />
          ) : (
            <AgentDetail sessionId={sessionId} agentNum={activePage} agentStatus={status.agent_status} />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
