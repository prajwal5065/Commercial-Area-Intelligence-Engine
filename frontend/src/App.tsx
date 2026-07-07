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
    <div className="h-screen flex flex-col bg-canvas text-ink font-sans overflow-hidden selection:bg-primary/20 selection:text-primary">
      <header className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-hairline bg-canvas/80 backdrop-blur-md z-10 sticky top-0 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center font-sans font-bold text-on-primary text-base shadow-sm">
            CI
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-ink-strong">
              Commercial Area Intelligence Engine
            </h1>
            <p className="text-sm text-body mt-0.5">
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

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 shrink-0 border-r border-hairline p-4 bg-canvas-soft/30 overflow-y-auto hidden md:block">
          <button
            onClick={() => setActivePage("dashboard")}
            className={`w-full text-left px-4 py-3 rounded-md text-sm font-medium mb-4 transition-all duration-200 ${
              activePage === "dashboard"
                ? "bg-canvas-soft text-ink-strong shadow-sm border border-hairline"
                : "text-body hover:bg-canvas-soft hover:text-ink border border-transparent"
            }`}
          >
            Dashboard
          </button>
          
          <div className="mb-2 px-2 flex items-center gap-2">
            <h3 className="text-xs font-bold tracking-wider uppercase text-body-mid">
              Pipeline Stages
            </h3>
          </div>
          {status && (
            <PipelineRail
              agentStatus={status.agent_status}
              activeAgent={activePage === "dashboard" ? "" : activePage}
              onSelectAgent={setActivePage}
            />
          )}
        </aside>

        <main className="flex-1 p-6 md:p-8 w-full overflow-y-auto bg-canvas">
          <div className="max-w-[1400px] mx-auto w-full">
            {!sessionId || !status ? (
              <p className="text-sm text-body-mid font-mono">Connecting to pipeline…</p>
            ) : activePage === "dashboard" ? (
              <Dashboard sessionId={sessionId} status={status} refresh={refresh} />
            ) : (
              <AgentDetail sessionId={sessionId} agentNum={activePage} agentStatus={status.agent_status} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
