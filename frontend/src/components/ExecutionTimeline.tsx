import { CheckCircle2, PlayCircle, AlertTriangle, Circle } from "lucide-react";
import type { LogEntry } from "../lib/api";

function iconFor(level: string) {
  switch (level) {
    case "STAGE":
      return <PlayCircle className="w-4 h-4 text-primary" />;
    case "SUCCESS":
      return <CheckCircle2 className="w-4 h-4 text-status-done" />;
    case "ERROR":
      return <AlertTriangle className="w-4 h-4 text-status-error" />;
    case "RATE_LIMIT":
      return <AlertTriangle className="w-4 h-4 text-status-warn" />;
    default:
      return <Circle className="w-2 h-2 text-mute fill-current mx-1" />;
  }
}

/**
 * Timeline of pipeline events (agent started, completed, errors, rate
 * limits), derived directly from the existing log stream rather than a
 * separate data source - every log entry already carries a timestamp,
 * agent name, and level, which is exactly what a timeline needs.
 */
export function ExecutionTimeline({ logs }: { logs: LogEntry[] }) {
  const notable = logs.filter((l) =>
    ["STAGE", "SUCCESS", "ERROR", "RATE_LIMIT"].includes(l.level)
  );

  if (notable.length === 0) {
    return (
      <p className="text-sm text-body-mid py-6 text-center">
        No timeline events yet — start the pipeline to see agent stage transitions here.
      </p>
    );
  }

  return (
    <div className="flex flex-col scrollbar-thin overflow-y-auto max-h-[340px] pr-1">
      {notable.map((entry, i) => (
        <div key={i} className="flex gap-3 items-start py-2 border-b border-hairline last:border-0">
          <div className="shrink-0 mt-0.5">{iconFor(entry.level)}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-mono text-body-mid tabular-nums">{entry.ts}</span>
              <span className="text-xs font-semibold text-ink">{entry.agent}</span>
            </div>
            <p className="text-sm text-body mt-0.5 truncate">{entry.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
