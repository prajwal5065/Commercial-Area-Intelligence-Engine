import { StatChip } from "./ui";
import type { AgentDetail, AgentStatus } from "../lib/api";

interface ExecutionSummaryProps {
  agentStatus: Record<string, AgentStatus>;
  agentsDetail: Record<string, AgentDetail>;
  elapsed: string | null;
}

/**
 * Top summary metrics. Mapped onto what this pipeline actually is (5
 * sequential agents, each processing batches of items) rather than a
 * fabricated spawned-agent-tree model:
 *
 * - "Agents Created"        -> the pipeline's fixed 5 agents
 * - "Batches Created"       -> sum of input_count across agents (the real
 *                              unit of parallel work - e.g. Agent 2 batches
 *                              countries 3-at-a-time)
 * - "Instances Running"     -> sum of active_instances across all agents
 * - "Active / Completed / Failed" -> derived directly from agent_status
 * - "Total Execution Time"  -> status.elapsed (already tracked pipeline-wide)
 */
export function ExecutionSummary({ agentStatus, agentsDetail, elapsed }: ExecutionSummaryProps) {
  const statuses = Object.values(agentStatus).map((s) => (s ?? "").toLowerCase());
  const totalAgents = 5;
  const batchesCreated = Object.values(agentsDetail).reduce((sum, d) => sum + (d?.input_count ?? 0), 0);
  // NEW: Sum of actual live worker threads/browser instances across all active stages
  const instancesRunning = Object.values(agentsDetail).reduce((sum, d) => sum + (d?.active_instances ?? 0), 0);
  const activeCount = statuses.filter((s) => s === "running").length;
  const completedCount = statuses.filter((s) => s === "done").length;
  const failedCount = statuses.filter((s) => s === "failed" || s === "error").length;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
      <StatChip label="Agents" value={totalAgents} />
      <StatChip label="Batches Processed" value={batchesCreated} />
      <StatChip label="Instances Running" value={instancesRunning} tone={instancesRunning > 0 ? "running" : "default"} />
      <StatChip label="Active Stages" value={activeCount} tone={activeCount > 0 ? "running" : "default"} />
      <StatChip label="Completed" value={completedCount} tone={completedCount > 0 ? "done" : "default"} />
      <StatChip label="Failed" value={failedCount} tone={failedCount > 0 ? "error" : "default"} />
      <StatChip label="Total Time" value={elapsed ?? "—"} />
    </div>
  );
}
