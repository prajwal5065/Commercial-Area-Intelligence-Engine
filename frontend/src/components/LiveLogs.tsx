import { useMemo, useState } from "react";
import { Search, AlertTriangle } from "lucide-react";
import type { LogEntry } from "../lib/api";

const LEVEL_STYLES: Record<string, string> = {
  STAGE:      "text-primary font-semibold",
  SUCCESS:    "text-status-done",
  ERROR:      "text-status-error",
  WARN:       "text-status-warn",
  RATE_LIMIT: "text-status-warn font-semibold",
  METRIC:     "text-body-mid",
  INFO:       "text-body",
  EOF:        "text-mute italic",
};

const LEVEL_OPTIONS = ["INFO", "WARN", "ERROR", "SUCCESS", "STAGE", "RATE_LIMIT"];

/**
 * Live execution log with search (message text) and filter (by agent name,
 * by level). Search & Filters requirement from the spec - agent/sub-agent/
 * status/instance-id filtering is collapsed here to agent + level, since
 * this pipeline has no sub-agent or instance-id concept to filter by
 * separately (see AgentHierarchy's comment on the real structure).
 */
export function LiveLogs({ logs }: { logs: LogEntry[] }) {
  const [query, setQuery] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState("");

  const agentOptions = useMemo(
    () => [...new Set(logs.map((l) => l.agent))].sort(),
    [logs]
  );

  const filtered = useMemo(() => {
    return logs.filter((l) => {
      if (agentFilter && l.agent !== agentFilter) return false;
      if (levelFilter && l.level !== levelFilter) return false;
      if (query && !l.message.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [logs, agentFilter, levelFilter, query]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="w-3.5 h-3.5 text-body-mid absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search log messages…"
            className="w-full bg-canvas border border-ink/20 rounded-sm pl-8 pr-3 py-2 text-sm text-ink placeholder-body-mid focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="bg-canvas border border-ink/20 rounded-sm px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">All agents</option>
          {agentOptions.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="bg-canvas border border-ink/20 rounded-sm px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">All levels</option>
          {LEVEL_OPTIONS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-body-mid text-center py-8">
          {logs.length === 0 ? "Waiting for pipeline to start…" : "No log entries match your filters."}
        </p>
      ) : (
        <div className="font-mono text-xs space-y-0.5 overflow-y-auto max-h-[380px] pr-1 scrollbar-thin">
          {filtered.map((entry, i) => (
            <div key={i} className="flex gap-2 items-start leading-relaxed hover:bg-canvas-softer px-1.5 py-0.5 rounded-sm">
              <span className="text-body-mid shrink-0 tabular-nums w-16">{entry.ts}</span>
              <span className={`shrink-0 w-28 truncate flex items-center gap-1 ${LEVEL_STYLES[entry.level] || "text-body-mid"}`}>
                {entry.level === "RATE_LIMIT" && <AlertTriangle className="w-3 h-3 shrink-0" />}
                [{entry.level}]
              </span>
              <span className="shrink-0 w-32 truncate text-ink-mid">{entry.agent}</span>
              <span className={LEVEL_STYLES[entry.level] || "text-body"}>{entry.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
