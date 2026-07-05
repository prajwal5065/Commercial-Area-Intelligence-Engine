import { useEffect, useRef, useState, useCallback } from "react";
import { api, type SessionStatus, type LogEntry, type LlmProvider } from "../lib/api";
import { Download, Play, Square, RotateCcw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle2, Clock, Activity, Wand2, SlidersHorizontal } from "lucide-react";
import { StageConfigurator } from "../components/StageConfigurator";
import { ProviderToggle } from "../components/ProviderToggle";

interface Props {
  sessionId: string;
  status: SessionStatus;
  refresh: () => Promise<SessionStatus | null>;
}

const AGENT_LABELS: Record<string, string> = {
  "1": "Country Discovery",
  "2": "City Discovery",
  "3": "Zone Discovery",
  "4": "Sub-Area Mapping",
  "5": "Execution Engine",
};

const LEVEL_STYLES: Record<string, string> = {
  STAGE:      "text-signal-400 font-bold",
  SUCCESS:    "text-emerald-400",
  ERROR:      "text-red-400",
  WARN:       "text-amber-400",
  RATE_LIMIT: "text-amber-400 font-bold",
  METRIC:     "text-purple-400 font-semibold",
  INFO:       "text-ink-300",
  EOF:        "text-ink-500 italic",
};

function statusColor(s: string): string {
  const lower = s?.toLowerCase() ?? "";
  if (lower === "done")    return "text-emerald-400";
  if (lower === "running") return "text-signal-400 animate-pulse";
  if (lower === "failed" || lower === "error") return "text-red-400";
  if (lower === "skipped") return "text-ink-500";
  return "text-ink-500";
}

function statusDot(s: string): string {
  const lower = s?.toLowerCase() ?? "";
  if (lower === "done")    return "bg-emerald-400";
  if (lower === "running") return "bg-signal-400 animate-pulse";
  if (lower === "failed" || lower === "error") return "bg-red-400";
  return "bg-ink-600";
}

function progressPct(pipelineStatus: string, agentStatuses: Record<string, string>): number {
  if (pipelineStatus === "done") return 100;
  const agents = Object.values(agentStatuses);
  const done = agents.filter(s => s.toLowerCase() === "done").length;
  const running = agents.some(s => s.toLowerCase() === "running") ? 0.5 : 0;
  return Math.round(((done + running) / 5) * 100);
}

// ── Metric Card ─────────────────────────────────────────────────────────────
function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 bg-ink-900 border border-ink-800 rounded-xl min-w-[110px]">
      <span className="font-mono text-[9px] uppercase tracking-widest text-ink-500">{label}</span>
      <span className="font-mono text-lg font-bold text-ink-100 tabular-nums">{value}</span>
      {sub && <span className="text-[10px] text-ink-500">{sub}</span>}
    </div>
  );
}

// ── Agent Stage Row ─────────────────────────────────────────────────────────
function AgentStageRow({
  num, label, status, elapsed, outputCount, errors,
}: {
  num: string; label: string; status: string;
  elapsed?: string; outputCount?: number; errors?: string[];
}) {
  const [expanded, setExpanded] = useState(false);
  const lower = status.toLowerCase();
  const isDone    = lower === "done";
  const isRunning = lower === "running";
  const isFailed  = lower === "failed" || lower === "error";

  return (
    <div className={`rounded-xl border transition-all ${
      isRunning ? "border-signal-500/50 bg-signal-500/5" :
      isDone    ? "border-emerald-500/30 bg-emerald-500/5" :
      isFailed  ? "border-red-500/30 bg-red-500/5" :
                  "border-ink-800 bg-ink-900"
    }`}>
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => (errors?.length || outputCount) && setExpanded(e => !e)}
      >
        {/* Status indicator */}
        <div className={`w-2 h-2 rounded-full shrink-0 ${statusDot(status)}`} />

        {/* Agent number badge */}
        <div className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-xs font-mono font-bold ${
          isDone ? "bg-emerald-500/20 text-emerald-400" :
          isRunning ? "bg-signal-500/20 text-signal-400" :
          isFailed ? "bg-red-500/20 text-red-400" :
          "bg-ink-800 text-ink-500"
        }`}>
          {num}
        </div>

        {/* Label */}
        <div className="flex-1">
          <p className={`text-sm font-medium ${statusColor(status)}`}>{label}</p>
          {isRunning && (
            <p className="text-xs text-signal-400 font-mono animate-pulse">Processing…</p>
          )}
        </div>

        {/* Right side */}
        <div className="flex items-center gap-3 text-xs font-mono">
          {elapsed && elapsed !== "—" && (
            <span className="text-ink-500 flex items-center gap-1">
              <Clock className="w-3 h-3" /> {elapsed}
            </span>
          )}
          {outputCount !== undefined && outputCount > 0 && (
            <span className={`font-semibold ${isDone ? "text-emerald-400" : "text-ink-400"}`}>
              {outputCount.toLocaleString()} records
            </span>
          )}
          {(errors?.length || false) && (
            expanded ? <ChevronUp className="w-3.5 h-3.5 text-ink-500" /> :
                       <ChevronDown className="w-3.5 h-3.5 text-ink-500" />
          )}
        </div>
      </div>

      {/* Expanded errors */}
      {expanded && errors && errors.length > 0 && (
        <div className="px-4 pb-3 border-t border-ink-800 pt-2">
          {errors.map((e, i) => (
            <p key={i} className="text-xs text-red-400 font-mono">{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Log Console ─────────────────────────────────────────────────────────────
function LogConsole({ logs, autoScroll }: { logs: LogEntry[]; autoScroll: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  if (logs.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-ink-500 text-sm font-mono">
        Waiting for pipeline to start…
      </div>
    );
  }

  return (
    <div className="font-mono text-xs space-y-0.5 overflow-y-auto max-h-[420px] pr-1">
      {logs.map((entry, i) => (
        <div key={i} className="flex gap-2 items-start leading-relaxed hover:bg-ink-800/30 px-1 rounded">
          <span className="text-ink-600 shrink-0 tabular-nums w-16">{entry.ts}</span>
          <span className={`shrink-0 w-16 truncate flex items-center gap-1 ${LEVEL_STYLES[entry.level] || "text-ink-400"}`}>
            {entry.level === "RATE_LIMIT" && <AlertTriangle className="w-3 h-3 shrink-0" />}
            [{entry.level}]
          </span>
          <span className={LEVEL_STYLES[entry.level] || "text-ink-300"}>{entry.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════
export function Dashboard({ sessionId, status, refresh }: Props) {
  const [topN, setTopN] = useState("5");
  const [skipSupabase, setSkipSupabase] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showLogs, setShowLogs] = useState(true);
  const [starting, setStarting] = useState(false);
  const esRef = useRef<EventSource | null>(null);

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
  const [stage4Provider, setStage4Provider] = useState<LlmProvider>("groq");
  const [manualStarting, setManualStarting] = useState<string | null>(null);

  const isRunning = status.running;
  const pStatus   = status.pipeline_status ?? "idle";
  const isDone    = pStatus === "done";
  const isFailed  = pStatus === "failed";
  const isIdle    = pStatus === "idle" || pStatus === "initializing";
  const counts    = status.counts ?? {};
  const sys       = status.system ?? {};
  const agents    = status.agents_detail ?? {};
  const progress  = progressPct(pStatus, status.agent_status);

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

  // ── Load existing logs when session has history ────────────────────────
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
    // Reset then restart in one click
    esRef.current?.close();
    setLogs([]);
    await api.resetSession(sessionId);
    await refresh();
    setStarting(true);
    try {
      await api.runFullPipeline(sessionId, {
        top_n: parseInt(topN, 10) || null,
        skip_supabase: skipSupabase,
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
      await api.runAgent3(sessionId, selectedCities);
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
    <div className="flex flex-col gap-6">

      {/* ── Header Control Bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink-100">Pipeline Control</h2>
          <p className="text-xs text-ink-500 mt-0.5">
            {isDone   ? `Completed in ${status.elapsed}` :
             isFailed ? `Failed at ${status.failed_agent ?? "unknown agent"}` :
             isRunning ? `Running — ${status.elapsed ?? "…"}` :
             "Ready to run"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!isRunning && !isDone && !isFailed && (
            <div className="flex items-center rounded-lg bg-ink-850 border border-ink-700 p-0.5">
              <button
                onClick={() => setRunMode("auto")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                  runMode === "auto" ? "bg-signal-500 text-ink-950" : "text-ink-400 hover:text-ink-200"
                }`}
              >
                <Wand2 className="w-3.5 h-3.5" />
                Auto
              </button>
              <button
                onClick={() => setRunMode("manual")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                  runMode === "manual" ? "bg-signal-500 text-ink-950" : "text-ink-400 hover:text-ink-200"
                }`}
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
                Manual
              </button>
            </div>
          )}
          <div className="flex items-center gap-2">
          {!isRunning && !isDone && !isFailed && runMode === "auto" && (
            <button
              onClick={handleStart}
              disabled={starting || isRunning}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-signal-500 text-ink-950 font-bold text-sm hover:bg-signal-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-signal-500/20"
            >
              <Play className="w-4 h-4" />
              Start Pipeline
            </button>
          )}
          {isRunning && (
            <button
              onClick={handleStop}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 text-red-400 border border-red-500/30 font-medium text-sm hover:bg-red-500/20 transition-all"
            >
              <Square className="w-3.5 h-3.5" />
              Stop
            </button>
          )}
          {runMode === "manual" && manualStarting !== null && (
            <button
              onClick={handleStop}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 text-red-400 border border-red-500/30 font-medium text-sm hover:bg-red-500/20 transition-all"
            >
              <Square className="w-3.5 h-3.5" />
              Stop
            </button>
          )}
          {(isDone || isFailed) && (
            <>
              {isDone && status.output_file && (
                <a href={api.downloadUrl(sessionId)} download>
                  <button className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium text-sm hover:bg-emerald-500/20 transition-all">
                    <Download className="w-3.5 h-3.5" />
                    Download Results
                  </button>
                </a>
              )}
              {isFailed && (
                <button
                  onClick={handleRetry}
                  disabled={starting}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-signal-500 text-ink-950 font-bold text-sm hover:bg-signal-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-signal-500/20"
                >
                  <Play className="w-4 h-4" />
                  Retry Pipeline
                </button>
              )}
              <button
                onClick={handleReset}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-ink-800 text-ink-300 border border-ink-700 font-medium text-sm hover:bg-ink-700 transition-all"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </button>
            </>
          )}
          {runMode === "manual" && !isDone && !isFailed && stage1Done && (
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-ink-800 text-ink-300 border border-ink-700 font-medium text-sm hover:bg-ink-700 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset
            </button>
          )}
          </div>
        </div>
      </div>

      {/* ── Pipeline Config: Auto mode (only when idle) ───────────────── */}
      {!isRunning && isIdle && runMode === "auto" && (
        <div className="bg-ink-900 border border-ink-800 rounded-xl p-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
              Top N Countries
            </label>
            <input
              value={topN}
              onChange={e => setTopN(e.target.value)}
              className="w-28 bg-ink-850 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:border-signal-500 focus:outline-none"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer pb-1">
            <input
              type="checkbox"
              checked={skipSupabase}
              onChange={e => setSkipSupabase(e.target.checked)}
              className="w-4 h-4 accent-signal-500"
            />
            <span className="text-sm text-ink-300">Skip Supabase (offline mode)</span>
          </label>
        </div>
      )}

      {/* ── Pipeline Config: Manual mode — configure & run each stage ──── */}
      {!isRunning && runMode === "manual" && (
        <div className="flex flex-col gap-4">
          {/* Stage 1: Countries */}
          <div className="bg-ink-900 border border-ink-800 rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-100">
                1 · Country Discovery
                {stage1Done && <span className="ml-2 text-xs font-normal text-emerald-400">Done</span>}
              </h3>
              <button
                onClick={handleManualRun1}
                disabled={manualStarting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-signal-500 text-ink-950 text-xs font-bold hover:bg-signal-400 disabled:opacity-50 transition-all"
              >
                <Play className="w-3 h-3" />
                {manualStarting === "1" ? "Running…" : stage1Done ? "Re-run" : "Run"}
              </button>
            </div>
            <StageConfigurator
              label="Countries"
              numberLabel="e.g. 10"
              numberValue={manualTopN}
              onNumberChange={setManualTopN}
              nameOptions={[]}
              selectedNames={manualCountryNames}
              onSelectedNamesChange={setManualCountryNames}
              disabled={manualStarting !== null}
              allowFreeText
            />
            <p className="text-[11px] text-ink-500 -mt-1">
              Number mode ranks countries by GDP and takes the top N. Name mode lets you type
              specific countries directly (e.g. India, USA, Japan) — GDP ranking is skipped and
              exactly those countries are used.
            </p>
          </div>

          {/* Stage 2: Cities */}
          <div className={`bg-ink-900 border rounded-xl p-4 flex flex-col gap-3 ${stage1Done ? "border-ink-800" : "border-ink-800 opacity-50"}`}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-100">
                2 · City Discovery
                {stage2Done && <span className="ml-2 text-xs font-normal text-emerald-400">Done</span>}
              </h3>
              <button
                onClick={handleManualRun2}
                disabled={!stage1Done || manualStarting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-signal-500 text-ink-950 text-xs font-bold hover:bg-signal-400 disabled:opacity-40 transition-all"
              >
                <Play className="w-3 h-3" />
                {manualStarting === "2" ? "Running…" : stage2Done ? "Re-run" : "Run"}
              </button>
            </div>
            <StageConfigurator
              label="Cities"
              numberLabel="e.g. 10"
              numberValue={manualCityTopN}
              onNumberChange={setManualCityTopN}
              nameOptions={countryOptions}
              selectedNames={selectedCountries}
              onSelectedNamesChange={setSelectedCountries}
              disabled={!stage1Done || manualStarting !== null}
            />
            <p className="text-[11px] text-ink-500 -mt-1">
              Name mode filters to specific countries (e.g. India, USA, Japan) discovered in Stage 1
              before running city segmentation on them.
            </p>
            <ProviderToggle
              value={stage2Provider}
              onChange={setStage2Provider}
              disabled={!stage1Done || manualStarting !== null}
              rateLimited={status.rate_limited_providers}
            />
          </div>

          {/* Stage 3: Zones */}
          <div className={`bg-ink-900 border rounded-xl p-4 flex flex-col gap-3 ${stage2Done ? "border-ink-800" : "border-ink-800 opacity-50"}`}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-100">
                3 · Zone Discovery
                {stage3Done && <span className="ml-2 text-xs font-normal text-emerald-400">Done</span>}
              </h3>
              <button
                onClick={handleManualRun3}
                disabled={!stage2Done || manualStarting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-signal-500 text-ink-950 text-xs font-bold hover:bg-signal-400 disabled:opacity-40 transition-all"
              >
                <Play className="w-3 h-3" />
                {manualStarting === "3" ? "Running…" : stage3Done ? "Re-run" : "Run"}
              </button>
            </div>
            <StageConfigurator
              label="Cities to zone-map"
              numberLabel="e.g. 10"
              numberValue={manualZoneTopN}
              onNumberChange={setManualZoneTopN}
              nameOptions={cityOptions}
              selectedNames={selectedCities}
              onSelectedNamesChange={setSelectedCities}
              disabled={!stage2Done || manualStarting !== null}
            />
          </div>

          {/* Stage 4: Sub-areas */}
          <div className={`bg-ink-900 border rounded-xl p-4 flex flex-col gap-3 ${stage3Done ? "border-ink-800" : "border-ink-800 opacity-50"}`}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-100">
                4 · Sub-Area Mapping
                {stage4Done && <span className="ml-2 text-xs font-normal text-emerald-400">Done</span>}
              </h3>
              <button
                onClick={handleManualRun4}
                disabled={!stage3Done || manualStarting !== null}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-signal-500 text-ink-950 text-xs font-bold hover:bg-signal-400 disabled:opacity-40 transition-all"
              >
                <Play className="w-3 h-3" />
                {manualStarting === "4" ? "Running…" : stage4Done ? "Re-run" : "Run"}
              </button>
            </div>
            <StageConfigurator
              label="Zones to sub-area map"
              numberLabel="e.g. 10"
              numberValue={manualSubareaTopN}
              onNumberChange={setManualSubareaTopN}
              nameOptions={zoneOptions}
              selectedNames={selectedZones}
              onSelectedNamesChange={setSelectedZones}
              disabled={!stage3Done || manualStarting !== null}
            />
            <ProviderToggle
              value={stage4Provider}
              onChange={setStage4Provider}
              disabled={!stage3Done || manualStarting !== null}
              rateLimited={status.rate_limited_providers}
            />
          </div>

          {/* Stage 5: Scraper */}
          <div className={`bg-ink-900 border rounded-xl p-4 flex items-center justify-between ${stage4Done ? "border-ink-800" : "border-ink-800 opacity-50"}`}>
            <div>
              <h3 className="text-sm font-semibold text-ink-100">
                5 · Execution Engine (Lead Scraper)
              </h3>
              <p className="text-[11px] text-ink-500 mt-0.5">
                Scrapes company data for all mapped sub-areas from the previous stage.
              </p>
            </div>
            <button
              onClick={handleManualRun5}
              disabled={!stage4Done || manualStarting !== null}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-signal-500 text-ink-950 text-xs font-bold hover:bg-signal-400 disabled:opacity-40 transition-all shrink-0"
            >
              <Play className="w-3.5 h-3.5" />
              {manualStarting === "5" ? "Running…" : "Run Scraper"}
            </button>
          </div>

          {(status.agent_status["5"] ?? "").toLowerCase() === "done" && (
            <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-3">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <p className="text-sm font-medium text-emerald-400 flex-1">
                All stages complete — {counts.companies?.toLocaleString() ?? 0} companies found.
              </p>
              {status.output_file && (
                <a href={api.downloadUrl(sessionId)} download>
                  <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium text-xs hover:bg-emerald-500/20 transition-all">
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </button>
                </a>
              )}
            </div>
          )}
        </div>
      )}


      {/* ── Progress Bar ───────────────────────────────────────────────── */}
      {(isRunning || isDone || isFailed) && (
        <div>
          <div className="flex justify-between text-xs font-mono text-ink-500 mb-1.5">
            <span>Pipeline Progress</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 bg-ink-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                isFailed ? "bg-red-500" :
                isDone   ? "bg-emerald-500" :
                           "bg-signal-500"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* ── Error Banner ───────────────────────────────────────────────── */}
      {(status.error || isFailed) && (
        <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-400">
              Pipeline Failed{status.failed_agent ? ` — ${status.failed_agent}` : ""}
            </p>
            {status.error && (
              <p className="text-xs text-red-400/70 mt-1 font-mono">{status.error}</p>
            )}
          </div>
        </div>
      )}

      {isDone && (
        <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-3">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <p className="text-sm font-medium text-emerald-400">
            Pipeline completed successfully in {status.elapsed} —{" "}
            {counts.companies?.toLocaleString() ?? 0} companies found
          </p>
        </div>
      )}

      {/* ── Metrics Row ────────────────────────────────────────────────── */}
      {(isRunning || isDone || isFailed || (runMode === "manual" && stage1Done)) && (
        <div className="flex flex-wrap gap-3">
          <MetricCard label="Countries" value={counts.countries ?? 0} />
          <MetricCard label="Cities" value={counts.cities ?? 0} />
          <MetricCard label="Zones" value={counts.zones ?? 0} />
          <MetricCard label="Sub-Areas" value={counts.subareas ?? 0} />
          <MetricCard label="Companies" value={counts.companies?.toLocaleString() ?? 0} />
          <MetricCard label="Duplicates" value={counts.duplicates_removed ?? 0} sub="removed" />
          <MetricCard label="Supabase" value={counts.supabase_inserted ?? 0} sub="inserted" />
          {sys.cpu_now !== undefined && (
            <MetricCard label="CPU" value={`${sys.cpu_now?.toFixed(0)}%`} sub={`peak ${sys.peak_cpu?.toFixed(0)}%`} />
          )}
          {sys.mem_mb !== undefined && (
            <MetricCard label="Memory" value={`${sys.mem_mb?.toFixed(0)} MB`} sub={`peak ${sys.peak_mem_mb?.toFixed(0)} MB`} />
          )}
        </div>
      )}

      {/* ── Agent Pipeline Stages ─────────────────────────────────────── */}
      {(isRunning || isDone || isFailed || (runMode === "manual" && stage1Done)) && (
        <div className="bg-ink-900 border border-ink-800 rounded-xl">
          <div className="px-5 py-4 border-b border-ink-800">
            <h3 className="text-sm font-semibold text-ink-100">Agent Pipeline</h3>
          </div>
          <div className="p-4 flex flex-col gap-2">
            {["1", "2", "3", "4", "5"].map(num => {
              const detail = agents[num];
              const legacyStatus = status.agent_status[num] ?? "pending";
              const agentStatus = detail?.status ?? legacyStatus;
              return (
                <AgentStageRow
                  key={num}
                  num={num}
                  label={AGENT_LABELS[num]}
                  status={agentStatus}
                  elapsed={detail?.elapsed}
                  outputCount={detail?.output_count}
                  errors={detail?.errors}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* ── Live Log Console ───────────────────────────────────────────── */}
      {(isRunning || isDone || isFailed || logs.length > 0) && (
        <div className="bg-ink-950 border border-ink-800 rounded-xl">
          <div className="flex items-center justify-between px-5 py-3 border-b border-ink-800">
            <div className="flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-signal-400" />
              <h3 className="text-sm font-semibold text-ink-100">Live Execution Log</h3>
              {(isRunning || (runMode === "manual" && manualStarting !== null)) && (
                <span className="flex items-center gap-1 text-xs text-signal-400 font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-signal-400 animate-pulse" />
                  LIVE
                </span>
              )}
              <span className="text-xs text-ink-600 font-mono">{logs.length} entries</span>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs text-ink-500 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={e => setAutoScroll(e.target.checked)}
                  className="w-3 h-3 accent-signal-500"
                />
                Auto-scroll
              </label>
              <button
                onClick={() => setShowLogs(v => !v)}
                className="text-xs text-ink-500 hover:text-ink-300 font-mono"
              >
                {showLogs ? "Hide" : "Show"}
              </button>
            </div>
          </div>
          {showLogs && (
            <div className="p-4">
              <LogConsole logs={logs} autoScroll={autoScroll} />
            </div>
          )}
        </div>
      )}

      {/* ── Idle state hint ───────────────────────────────────────────── */}
      {isIdle && logs.length === 0 && runMode === "auto" && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-signal-500/10 border border-signal-500/20 flex items-center justify-center mb-4">
            <Play className="w-7 h-7 text-signal-400" />
          </div>
          <h3 className="text-base font-semibold text-ink-200 mb-2">
            Ready to discover companies
          </h3>
          <p className="text-sm text-ink-500 max-w-sm">
            Click <strong className="text-signal-400">Start Pipeline</strong> to begin the automated
            multi-agent discovery process. All 5 agents will run automatically.
          </p>
        </div>
      )}
    </div>
  );
}
