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
    <div className="min-h-screen bg-canvas text-ink font-sans">
      <header className="flex items-center justify-between px-6 py-4 border-b border-hairline bg-canvas">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center font-mono font-bold text-on-primary text-sm">
            CI
          </div>
          <div>
            <h1 className="text-xl font-normal tracking-[-0.6px] leading-none text-ink-strong">
              Commercial Area Intelligence Engine
            </h1>
            <p className="text-sm text-body mt-1">
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
        <aside className="w-64 shrink-0 border-r border-hairline min-h-[calc(100vh-73px)] p-3 bg-canvas">
          <button
            onClick={() => setActivePage("dashboard")}
            className={`w-full text-left px-4 py-2.5 rounded-sm text-sm font-medium mb-2 transition-colors ${
              activePage === "dashboard"
                ? "bg-canvas-soft text-ink-strong"
                : "text-body hover:bg-canvas-soft hover:text-ink"
            }`}
          >
            Dashboard
          </button>
          <div className="my-3 border-t border-hairline" />
          <p className="px-4 text-sm font-semibold tracking-[2.52px] uppercase text-body mb-2">
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
