import { Badge, ProgressBar } from "./ui";
import type { AgentDetail, AgentStatus } from "../lib/api";

function fmtTime(unixSecs: number | null): string {
  if (!unixSecs) return "—";
  return new Date(unixSecs * 1000).toLocaleTimeString();
}

function statusTone(status: string | undefined): "default" | "running" | "done" | "error" | "pending" {
  const s = (status ?? "").toLowerCase();
  if (s === "running") return "running";
  if (s === "done") return "done";
  if (s === "failed" || s === "error") return "error";
  return "pending";
}

function progressFor(detail: AgentDetail | undefined, status: AgentStatus | undefined): number {
  const s = (status ?? "").toLowerCase();
  if (s === "done") return 100;
  if (s === "failed" || s === "error") return 100;
  if (s === "pending" || !detail) return 0;
  if (!detail.input_count) return s === "running" ? 50 : 0;
  return Math.min(100, Math.round((detail.output_count / detail.input_count) * 100));
}

const AGENT_LABELS: Record<string, string> = {
  "1": "Country Discovery",
  "2": "City Discovery",
  "3": "Zone Discovery",
  "4": "Sub-Area Mapping",
  "5": "Execution Engine",
};

/**
 * Per-agent instance/batch details: count processed, status, start/end,
 * duration, retry/error counts. "Instance" here means a processed batch
 * (the real parallel-work unit in this pipeline - see AgentHierarchy's
 * comment), not a fabricated spawned sub-process. Session-wide memory
 * (system.mem_mb) is shown where available; there's no genuine per-agent
 * token/memory metric in this backend, so none is fabricated here.
 */
export function InstanceDetails({
  agentId,
  status,
  detail,
  memMb,
}: {
  agentId: string;
  status: AgentStatus | undefined;
  detail: AgentDetail | undefined;
  memMb?: number;
}) {
  const progress = progressFor(detail, status);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-ink">
          Agent {agentId} — {AGENT_LABELS[agentId] ?? "Unknown"}
        </h3>
        <Badge tone={statusTone(status)}>{status ?? "Pending"}</Badge>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] font-semibold tracking-[2.52px] uppercase text-body">Progress</span>
          <span className="text-xs font-semibold text-ink tabular-nums">{progress}%</span>
        </div>
        <ProgressBar value={progress} tone={statusTone(status) === "error" ? "error" : statusTone(status) === "done" ? "done" : "primary"} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        <Field label="Items In (batch size)" value={detail?.input_count?.toString() ?? "—"} />
        <Field label="Items Out (produced)" value={detail?.output_count?.toString() ?? "—"} />
        <Field label="Start Time" value={fmtTime(detail?.start_time ?? null)} />
        <Field label="End Time" value={fmtTime(detail?.end_time ?? null)} />
        <Field label="Duration" value={detail?.elapsed ?? "—"} />
        <Field label="Retry Count" value={detail?.retry_count?.toString() ?? "0"} highlight={!!detail?.retry_count} />
        <Field label="Error Count" value={detail?.error_count?.toString() ?? "0"} highlight={!!detail?.error_count} isError={!!detail?.error_count} />
        {memMb !== undefined && <Field label="Session Memory" value={`${memMb.toFixed(0)} MB`} />}
      </div>

      {detail && detail.errors.length > 0 && (
        <div className="bg-status-error-bg border border-status-error rounded-md p-3">
          <p className="text-[11px] font-semibold tracking-[2.52px] uppercase text-status-error mb-1.5">
            Recent Errors
          </p>
          <ul className="text-sm text-status-error space-y-1">
            {detail.errors.slice(-5).map((e, i) => (
              <li key={i} className="truncate">• {e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  highlight,
  isError,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  isError?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-semibold tracking-[2.52px] uppercase text-body">{label}</span>
      <span
        className={`font-semibold tabular-nums ${
          highlight ? (isError ? "text-status-error" : "text-status-warn") : "text-ink"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
