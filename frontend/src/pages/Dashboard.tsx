import { useEffect, useRef, useState, useCallback } from "react";
import { api, type SessionStatus, type LogEntry, type LlmProvider } from "../lib/api";
import { Download, Play, Square, RotateCcw, Wand2, SlidersHorizontal } from "lucide-react";
import { StageConfigurator } from "../components/StageConfigurator";
import { ProviderToggle } from "../components/ProviderToggle";
import { Card, Button, Badge, ProgressBar } from "../components/ui";
import { ExecutionSummary } from "../components/ExecutionSummary";
import { AgentHierarchy } from "../components/AgentHierarchy";
import { InstanceDetails } from "../components/InstanceDetails";
import { ExecutionTimeline } from "../components/ExecutionTimeline";
import { LiveLogs } from "../components/LiveLogs";

interface Props {
  sessionId: string;
  status: SessionStatus;
  refresh: () => Promise<SessionStatus | null>;
}

function progressPct(pipelineStatus: string, agentStatuses: Record<string, string>): number {
  if (pipelineStatus === "done") return 100;
  const agents = Object.values(agentStatuses);
  const done = agents.filter(s => s.toLowerCase() === "done").length;
  const running = agents.some(s => s.toLowerCase() === "running") ? 0.5 : 0;
  return Math.round(((done + running) / 5) * 100);
}

// ═══════════════════════════════════════════════════════════════════════════
//  DASHBOARD — single-page execution monitor
// ═══════════════════════════════════════════════════════════════════════════
export function Dashboard({ sessionId, status, refresh }: Props) {
  const [topN, setTopN] = useState("5");
  const [skipSupabase, setSkipSupabase] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [starting, setStarting] = useState(false);
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Which agent is selected in the hierarchy view (drives Instance Details panel)
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // ── Manual (stage-by-stage) run mode ─────────────────────────────────
  const [runMode, setRunMode] = useState<"auto" | "manual">("auto");
  const [manualTopN, setManualTopN] = useState("10");
  const [manualCountryNames, setManualCountryNames] = useState<string[]>([]);
  const [countryOptions, setCountryOptions] = useState<string[]>([]);
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [manualCityTopN, setManualCityTopN] = useState("10");
  const [cityOptions, setCityOptions] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [manualZoneTopN, setManualZoneTopN] = useState("10");
  const [zoneOptions, setZoneOptions] = useState<string[]>([]);
  const [selectedZones, setSelectedZones] = useState<string[]>([]);
  const [manualSubareaTopN, setManualSubareaTopN] = useState("10");
  const [stage2Provider, setStage2Provider] = useState<LlmProvider>("groq");
  const [stage3Provider, setStage3Provider] = useState<LlmProvider>("groq");
  const [stage4Provider, setStage4Provider] = useState<LlmProvider>("groq");
  const [manualStarting, setManualStarting] = useState<string | null>(null);

  const isRunning = status.running;
  const pStatus   = status.pipeline_status ?? "idle";
  const isDone    = pStatus === "done";
  const isFailed  = pStatus === "failed";
  const isIdle    = pStatus === "idle" || pStatus === "initializing";
  const sys       = status.system ?? {};
  const agents    = status.agents_detail ?? {};
  const progress  = progressPct(pStatus, status.agent_status);

  // Default the selected agent to whichever is currently running, or "1"
  useEffect(() => {
    if (selectedAgent) return;
    const runningAgent = Object.entries(status.agent_status).find(
      ([, s]) => (s ?? "").toLowerCase() === "running"
    );
    setSelectedAgent(runningAgent?.[0] ?? "1");
  }, [status.agent_status, selectedAgent]);

  // ── Auto-refresh status every 3s while running — keeps metric cards live
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => { refresh(); }, 3000);
    return () => clearInterval(interval);
  }, [isRunning, refresh]);

  // ── SSE log stream ─────────────────────────────────────────────────────
  const startStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }
    const es = new EventSource(api.logsStreamUrl(sessionId));
    esRef.current = es;
    es.onmessage = (evt) => {
      try {
        const entry: LogEntry = JSON.parse(evt.data);
        if (entry.level === "EOF") {
          es.close();
          return;
        }
        if (entry.message.startsWith("PROVIDER_FALLBACK_TRIGGERED:")) {
          const newProvider = entry.message.split(":")[1] as LlmProvider;
          setStage2Provider(newProvider);
          setStage3Provider(newProvider);
          setStage4Provider(newProvider);
          localStorage.setItem("active_provider", newProvider);
          setFallbackNotice(`Automatically switched to ${newProvider.toUpperCase()} because the previously selected provider failed.`);
          // Also remove the log so it doesn't clutter the UI directly, or keep it.
          // Let's just keep it in logs but also show the notice.
        }

        setLogs(prev => [...prev.slice(-1999), entry]);
      } catch { /* ignore malformed */ }
    };
    es.onerror = () => {
      es.close();
    };
  }, [sessionId]);

  useEffect(() => {
    return () => { esRef.current?.close(); };
  }, []);

  useEffect(() => {
    if (isRunning) {
      startStream();
    }
  }, [isRunning, startStream]);

  useEffect(() => {
    if (runMode === "manual" && manualStarting !== null && !esRef.current) {
      startStream();
    }
  }, [runMode, manualStarting, startStream]);

  // ── Handlers ──────────────────────────────────────────────────────────
  async function handleStart() {
    setStarting(true);
    setLogs([]);
    try {
      await api.runFullPipeline(sessionId, {
        top_n: parseInt(topN, 10) || null,
        skip_supabase: skipSupabase,
        stage2_provider: stage2Provider,
        stage3_provider: stage3Provider,
        stage4_provider: stage4Provider,
      });
      startStream();
      refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    await api.stopPipeline(sessionId);
    refresh();
  }

  async function handleReset() {
    esRef.current?.close();
    setLogs([]);
    await api.resetSession(sessionId);
    refresh();
  }

  async function handleRetry() {
    esRef.current?.close();
    setLogs([]);
    await api.resetSession(sessionId);
    await refresh();
    setStarting(true);
    try {
      await api.runFullPipeline(sessionId, {
        top_n: parseInt(topN, 10) || null,
        skip_supabase: skipSupabase,
        stage2_provider: stage2Provider,
        stage3_provider: stage3Provider,
        stage4_provider: stage4Provider,
      });
      startStream();
      refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setStarting(false);
    }
  }

  // ── Manual stage-by-stage handlers ───────────────────────────────────
  const stage1Done = (status.agent_status["1"] ?? "").toLowerCase() === "done";
  const stage2Done = (status.agent_status["2"] ?? "").toLowerCase() === "done";
  const stage3Done = (status.agent_status["3"] ?? "").toLowerCase() === "done";
  const stage4Done = (status.agent_status["4"] ?? "").toLowerCase() === "done";

  const isAgent1Running = (status.agent_status["1"] ?? "").toLowerCase() === "running" || manualStarting === "1";
  const isAgent2Running = (status.agent_status["2"] ?? "").toLowerCase() === "running" || manualStarting === "2";
  const isAgent3Running = (status.agent_status["3"] ?? "").toLowerCase() === "running" || manualStarting === "3";
  const isAgent4Running = (status.agent_status["4"] ?? "").toLowerCase() === "running" || manualStarting === "4";
  const isAgent5Running = (status.agent_status["5"] ?? "").toLowerCase() === "running" || manualStarting === "5";

  useEffect(() => {
    if (runMode !== "manual" || !stage1Done) return;
    api.getCountries(sessionId).then((rows) =>
      setCountryOptions(rows.map((r) => r.country_name).filter((v): v is string => !!v))
    ).catch(() => {});
  }, [runMode, stage1Done, sessionId]);

  useEffect(() => {
    if (runMode !== "manual" || !stage2Done) return;
    api.getCities(sessionId).then((rows) =>
      setCityOptions([...new Set(rows.map((r) => r.city).filter((v): v is string => !!v))])
    ).catch(() => {});
  }, [runMode, stage2Done, sessionId]);

  useEffect(() => {
    if (runMode !== "manual" || !stage3Done) return;
    api.getZones(sessionId).then((rows) =>
      setZoneOptions([...new Set(rows.map((r) => r.zone_name))])
    ).catch(() => {});
  }, [runMode, stage3Done, sessionId]);

  async function handleManualRun1() {
    setManualStarting("1");
    try {
      await api.runAgent1(
        sessionId,
        manualCountryNames.length ? null : parseInt(manualTopN, 10) || null,
        manualCountryNames
      );
      refresh();
    } finally {
      setManualStarting(null);
    }
  }
  async function handleManualRun2() {
    setManualStarting("2");
    try {
      await api.runAgent2(sessionId, selectedCountries, stage2Provider);
      refresh();
    } finally {
      setManualStarting(null);
    }
  }
  async function handleManualRun3() {
    setManualStarting("3");
    try {
      await api.runAgent3(sessionId, selectedCities, stage3Provider);
      refresh();
    } finally {
      setManualStarting(null);
    }
  }
  async function handleManualRun4() {
    setManualStarting("4");
    try {
      await api.runAgent4(sessionId, selectedZones, stage4Provider);
      refresh();
    } finally {
      setManualStarting(null);
    }
  }
  async function handleManualRun5() {
    setManualStarting("5");
    try {
      await api.runAgent5(sessionId);
      refresh();
    } finally {
      setManualStarting(null);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {fallbackNotice && (
        <div className="mb-2 p-4 bg-status-running/10 border border-status-running rounded-lg text-sm text-status-running flex justify-between items-center">
          <span><strong>Notice:</strong> {fallbackNotice}</span>
          <button onClick={() => setFallbackNotice(null)} className="opacity-70 hover:opacity-100 text-lg">&times;</button>
        </div>
      )}
      {/* ── Execution Summary ─────────────────────────────────────────── */}
      <ExecutionSummary
        agentStatus={status.agent_status}
        agentsDetail={agents}
        elapsed={status.elapsed}
      />

      {/* ── Workflow Progress ─────────────────────────────────────────── */}
      <Card title="Workflow Progress">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-body">
            {isDone ? "Pipeline completed" : isFailed ? `Failed at ${status.failed_agent ?? "unknown agent"}` : isRunning ? "Running…" : "Ready to run"}
          </span>
          <span className="text-sm font-semibold text-ink tabular-nums">{progress}%</span>
        </div>
        <ProgressBar value={progress} tone={isFailed ? "error" : isDone ? "done" : "primary"} />

        {status.error && (
          <div className="mt-3 bg-status-error-bg border border-status-error/20 text-status-error rounded-md px-4 py-3 text-sm">
            {status.error}
          </div>
        )}

        {/* Run controls */}
        <div className="flex items-center justify-between flex-wrap gap-4 mt-6 pt-6 border-t border-hairline">
          {!isRunning && !isDone && !isFailed && (
            <div className="flex items-center rounded-lg bg-canvas-soft border border-hairline p-1 shadow-sm">
              <button
                onClick={() => setRunMode("auto")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-semibold transition-colors ${
                  runMode === "auto" ? "bg-primary text-on-primary" : "text-body hover:text-ink"
                }`}
              >
                <Wand2 className="w-3.5 h-3.5" />
                Auto
              </button>
              <button
                onClick={() => setRunMode("manual")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-semibold transition-colors ${
                  runMode === "manual" ? "bg-primary text-on-primary" : "text-body hover:text-ink"
                }`}
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
                Manual
              </button>
            </div>
          )}

          <div className="flex items-center gap-2 ml-auto">
            {!isRunning && !isDone && !isFailed && runMode === "auto" && (
              <Button variant="primary" onClick={handleStart} disabled={starting || isRunning}>
                <Play className="w-4 h-4" />
                Start Pipeline
              </Button>
            )}
            {isRunning && (
              <Button variant="danger" onClick={handleStop}>
                <Square className="w-3.5 h-3.5" />
                Stop
              </Button>
            )}
            {runMode === "manual" && manualStarting !== null && (
              <Button variant="danger" onClick={handleStop}>
                <Square className="w-3.5 h-3.5" />
                Stop
              </Button>
            )}
            {(isDone || isFailed) && (
              <>
                {isFailed && (
                  <Button variant="primary" onClick={handleRetry}>
                    <Play className="w-3.5 h-3.5" />
                    Retry Pipeline
                  </Button>
                )}
                {isDone && status.output_file && (
                  <a href={api.downloadUrl(sessionId)} download>
                    <Button variant="outline-on-dark">
                      <Download className="w-3.5 h-3.5" />
                      Download Results
                    </Button>
                  </a>
                )}
                <Button variant="outline-on-dark" onClick={handleReset}>
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset
                </Button>
              </>
            )}
            {runMode === "manual" && !isDone && !isFailed && stage1Done && (
              <Button variant="outline-on-dark" onClick={handleReset}>
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </Button>
            )}
          </div>
        </div>

        {/* Auto mode config */}
        {!isRunning && isIdle && runMode === "auto" && (
          <div className="mt-4 pt-4 border-t border-hairline flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-[11px] font-semibold tracking-[2.52px] uppercase text-body mb-1.5">
                Top N Countries
              </label>
              <input
                value={topN}
                onChange={e => setTopN(e.target.value)}
                className="w-28 bg-canvas border border-hairline rounded-sm px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer pb-1">
              <input
                type="checkbox"
                checked={skipSupabase}
                onChange={e => setSkipSupabase(e.target.checked)}
                className="w-4 h-4 accent-primary"
              />
              <span className="text-sm text-body">Skip Supabase (offline mode)</span>
            </label>
          </div>
        )}

        {/* Manual mode config panels */}
        {!isRunning && runMode === "manual" && (
          <div className="flex flex-col gap-5 mt-6 pt-6 border-t border-hairline">
            {/* Stage 1 */}
            <div className="bg-canvas-soft border border-hairline rounded-xl p-5 flex flex-col gap-4 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">
                  1 · Country Discovery
                  {stage1Done && <span className="ml-2 text-xs font-normal text-status-done">Done</span>}
                </h3>
                <Button variant="primary" onClick={handleManualRun1} disabled={manualStarting !== null || isAgent1Running} className="!text-xs !px-3 !py-1.5">
                  <Play className="w-3 h-3" />
                  {isAgent1Running ? "Running…" : stage1Done ? "Re-run" : "Run"}
                </Button>
              </div>
              <StageConfigurator
                label="Countries"
                numberLabel="e.g. 10"
                numberValue={manualTopN}
                onNumberChange={setManualTopN}
                nameOptions={[]}
                selectedNames={manualCountryNames}
                onSelectedNamesChange={setManualCountryNames}
                disabled={manualStarting !== null || isAgent1Running}
                allowFreeText
              />
              <p className="text-[11px] text-body-mid -mt-1">
                Number mode ranks countries by GDP and takes the top N. Name mode lets you type
                specific countries directly (e.g. India, USA, Japan) — GDP ranking is skipped and
                exactly those countries are used.
              </p>
            </div>

            {/* Stage 2 */}
            <div className={`bg-canvas-soft border rounded-xl p-5 flex flex-col gap-4 shadow-sm transition-opacity ${stage1Done ? "border-hairline" : "border-hairline opacity-50"}`}>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">
                  2 · City Discovery
                  {stage2Done && <span className="ml-2 text-xs font-normal text-status-done">Done</span>}
                </h3>
                <Button variant="primary" onClick={handleManualRun2} disabled={!stage1Done || manualStarting !== null || isAgent2Running} className="!text-xs !px-3 !py-1.5">
                  <Play className="w-3 h-3" />
                  {isAgent2Running ? "Running…" : stage2Done ? "Re-run" : "Run"}
                </Button>
              </div>
              <StageConfigurator
                label="Cities"
                numberLabel="e.g. 10"
                numberValue={manualCityTopN}
                onNumberChange={setManualCityTopN}
                nameOptions={countryOptions}
                selectedNames={selectedCountries}
                onSelectedNamesChange={setSelectedCountries}
                disabled={!stage1Done || manualStarting !== null || isAgent2Running}
              />
              <p className="text-[11px] text-body-mid -mt-1">
                Name mode filters to specific countries (e.g. India, USA, Japan) discovered in Stage 1
                before running city segmentation on them.
              </p>
              <ProviderToggle
                value={stage2Provider}
                onChange={setStage2Provider}
                disabled={!stage1Done || manualStarting !== null || isAgent2Running}
                rateLimited={status.rate_limited_providers}
              />
            </div>

            {/* Stage 3 */}
            <div className={`bg-canvas-soft border rounded-xl p-5 flex flex-col gap-4 shadow-sm transition-opacity ${stage2Done ? "border-hairline" : "border-hairline opacity-50"}`}>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">
                  3 · Zone Discovery
                  {stage3Done && <span className="ml-2 text-xs font-normal text-status-done">Done</span>}
                </h3>
                <Button variant="primary" onClick={handleManualRun3} disabled={!stage2Done || manualStarting !== null || isAgent3Running} className="!text-xs !px-3 !py-1.5">
                  <Play className="w-3 h-3" />
                  {isAgent3Running ? "Running…" : stage3Done ? "Re-run" : "Run"}
                </Button>
              </div>
              <StageConfigurator
                label="Cities to zone-map"
                numberLabel="e.g. 10"
                numberValue={manualZoneTopN}
                onNumberChange={setManualZoneTopN}
                nameOptions={cityOptions}
                selectedNames={selectedCities}
                onSelectedNamesChange={setSelectedCities}
                disabled={!stage2Done || manualStarting !== null || isAgent3Running}
              />
              <ProviderToggle
                value={stage3Provider}
                onChange={setStage3Provider}
                disabled={!stage2Done || manualStarting !== null || isAgent3Running}
                rateLimited={status.rate_limited_providers}
              />
            </div>

            {/* Stage 4 */}
            <div className={`bg-canvas-soft border rounded-xl p-5 flex flex-col gap-4 shadow-sm transition-opacity ${stage3Done ? "border-hairline" : "border-hairline opacity-50"}`}>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">
                  4 · Sub-Area Mapping
                  {stage4Done && <span className="ml-2 text-xs font-normal text-status-done">Done</span>}
                </h3>
                <Button variant="primary" onClick={handleManualRun4} disabled={!stage3Done || manualStarting !== null || isAgent4Running} className="!text-xs !px-3 !py-1.5">
                  <Play className="w-3 h-3" />
                  {isAgent4Running ? "Running…" : stage4Done ? "Re-run" : "Run"}
                </Button>
              </div>
              <StageConfigurator
                label="Zones to sub-area map"
                numberLabel="e.g. 10"
                numberValue={manualSubareaTopN}
                onNumberChange={setManualSubareaTopN}
                nameOptions={zoneOptions}
                selectedNames={selectedZones}
                onSelectedNamesChange={setSelectedZones}
                disabled={!stage3Done || manualStarting !== null || isAgent4Running}
              />
              <ProviderToggle
                value={stage4Provider}
                onChange={setStage4Provider}
                disabled={!stage3Done || manualStarting !== null || isAgent4Running}
                rateLimited={status.rate_limited_providers}
              />
            </div>

            {/* Stage 5 */}
            <div className={`bg-canvas-soft border rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm transition-opacity ${stage4Done ? "border-hairline" : "border-hairline opacity-50"}`}>
              <div>
                <h3 className="text-sm font-semibold text-ink">5 · Execution Engine (Lead Scraper)</h3>
                <p className="text-[11px] text-body-mid mt-0.5">
                  Scrapes company data for all mapped sub-areas from the previous stage.
                </p>
              </div>
              <Button variant="primary" onClick={handleManualRun5} disabled={!stage4Done || manualStarting !== null || isAgent5Running} className="!text-xs !px-4 !py-2">
                <Play className="w-3.5 h-3.5" />
                {isAgent5Running ? "Running…" : "Run Scraper"}
              </Button>
            </div>

            {(status.agent_status["5"] ?? "").toLowerCase() === "done" && (
              <div className="flex items-center gap-3 bg-status-done-bg border border-status-done/20 rounded-md px-4 py-3">
                <Badge tone="done">Complete</Badge>
                <p className="text-sm font-medium text-status-done flex-1">
                  All stages complete — {status.counts?.companies?.toLocaleString() ?? 0} companies found.
                </p>
                {status.output_file && (
                  <a href={api.downloadUrl(sessionId)} download>
                    <Button variant="outline-on-dark" className="!text-xs !px-3 !py-1.5">
                      <Download className="w-3.5 h-3.5" />
                      Download
                    </Button>
                  </a>
                )}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Agent Hierarchy + Selected Agent Instance Details ──────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card title="Agent Hierarchy">
          <AgentHierarchy
            agentStatus={status.agent_status}
            agentsDetail={agents}
            selectedAgent={selectedAgent}
            onSelectAgent={setSelectedAgent}
          />
        </Card>
        <Card title="Instance Details">
          {selectedAgent ? (
            <InstanceDetails
              agentId={selectedAgent}
              status={status.agent_status[selectedAgent]}
              detail={agents[selectedAgent]}
              memMb={sys.mem_mb}
            />
          ) : (
            <p className="text-sm text-body-mid text-center py-8">Select an agent from the hierarchy to see details.</p>
          )}
        </Card>
      </div>

      {/* ── Execution Timeline ──────────────────────────────────────────── */}
      <Card title="Execution Timeline">
        <ExecutionTimeline logs={logs} />
      </Card>

      {/* ── Live Logs (with search & filter) ───────────────────────────── */}
      <Card title="Live Execution Log" action={<span className="text-xs text-body-mid">{logs.length} entries</span>}>
        <LiveLogs logs={logs} />
      </Card>
    </div>
  );
}
