import { Badge } from "./ui";
import type { AgentDetail, AgentStatus } from "../lib/api";

const AGENT_LABELS: Record<string, string> = {
  "1": "Agent 1 — Country Discovery",
  "2": "Agent 2 — City Discovery",
  "3": "Agent 3 — Zone Discovery",
  "4": "Agent 4 — Sub-Area Mapping",
  "5": "Agent 5 — Execution Engine",
};

const AGENT_ORDER = ["1", "2", "3", "4", "5"];

function statusTone(status: string | undefined): "default" | "running" | "done" | "error" | "pending" {
  const s = (status ?? "").toLowerCase();
  if (s === "running") return "running";
  if (s === "done") return "done";
  if (s === "failed" || s === "error") return "error";
  return "pending";
}

interface AgentHierarchyProps {
  agentStatus: Record<string, AgentStatus>;
  agentsDetail: Record<string, AgentDetail>;
  selectedAgent: string | null;
  onSelectAgent: (id: string) => void;
}

/**
 * Visual hierarchy: Master Agent -> the 5 real pipeline agents -> that
 * agent's processed batches (the actual unit of parallel work in this
 * codebase - e.g. Agent 2 batches countries 3-at-a-time per worker thread).
 *
 * This intentionally does NOT show a fabricated "Sub-Agent" layer between
 * Agent and Batch - the pipeline has no such layer. "Batches processed"
 * (input_count/output_count from AgentMetrics) is the real analogue to
 * "instances" here, labeled honestly rather than invented.
 */
export function AgentHierarchy({ agentStatus, agentsDetail, selectedAgent, onSelectAgent }: AgentHierarchyProps) {
  return (
    <div className="font-mono text-sm">
      <div className="flex items-center gap-2 py-2">
        <span className="font-semibold text-ink">Master Agent</span>
        <span className="text-body-mid text-xs">(orchestrator)</span>
      </div>
      <div className="pl-2 border-l-2 border-hairline ml-2">
        {AGENT_ORDER.map((id, i) => {
          const status = agentStatus[id];
          const detail = agentsDetail[id];
          const isLast = i === AGENT_ORDER.length - 1;
          const isSelected = selectedAgent === id;
          const batchCount = detail?.input_count ?? 0;

          return (
            <div key={id} className="relative pl-5">
              <span className="absolute left-0 top-4 w-4 h-px bg-hairline" />
              {!isLast && <span className="absolute left-0 top-4 bottom-0 w-px bg-hairline" />}

              <button
                onClick={() => onSelectAgent(id)}
                className={`w-full text-left flex items-center justify-between gap-3 py-3 px-4 rounded-lg mb-2 transition-all duration-200 ${
                  isSelected ? "bg-primary/10 border border-primary/30 shadow-sm" : "hover:bg-canvas-soft border border-transparent"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-semibold text-ink truncate">{AGENT_LABELS[id]}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-body-mid">
                    {batchCount > 0 ? `${batchCount} item${batchCount === 1 ? "" : "s"}` : "—"}
                  </span>
                  <span className="text-xs text-body-mid tabular-nums">{detail?.elapsed ?? "—"}</span>
                  <Badge tone={statusTone(status)}>{status ?? "Pending"}</Badge>
                </div>
              </button>

              {/* Leaf: batches processed by this agent, when it has run */}
              {isSelected && detail && detail.output_count > 0 && (
                <div className="pl-5 pb-2 border-l-2 border-hairline ml-3 mb-2">
                  <div className="relative pl-5 py-1.5">
                    <span className="absolute left-0 top-1/2 w-4 h-px bg-hairline" />
                    <span className="text-xs text-body">
                      {detail.output_count} item{detail.output_count === 1 ? "" : "s"} produced
                      {detail.error_count > 0 && (
                        <span className="text-status-error"> · {detail.error_count} error{detail.error_count === 1 ? "" : "s"}</span>
                      )}
                      {detail.retry_count > 0 && (
                        <span className="text-status-warn"> · {detail.retry_count} retr{detail.retry_count === 1 ? "y" : "ies"}</span>
                      )}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
