import { useEffect, useState } from "react";
import { api, type AgentStatus } from "../lib/api";
import { Card, EmptyState, Badge } from "../components/ui";

const AGENT_NAMES: Record<string, string> = {
  "1": "GDP Ranker",
  "2": "City Segmenter",
  "3": "Zone Finder",
  "4": "Subarea Mapper",
  "5": "Lead Scraper",
};

function statusTone(status: AgentStatus | undefined): "default" | "running" | "done" | "error" | "pending" {
  const s = (status ?? "").toLowerCase();
  if (s === "done") return "done";
  if (s === "running") return "running";
  if (s === "error" || s === "failed") return "error";
  return "pending";
}

async function fetchAgentData(
  sessionId: string,
  agentNum: string
): Promise<Record<string, unknown>[]> {
  switch (agentNum) {
    case "1":
      return api.getCountries(sessionId) as Promise<Record<string, unknown>[]>;
    case "2":
      return api.getCities(sessionId) as Promise<Record<string, unknown>[]>;
    case "3":
      return api.getZones(sessionId) as Promise<Record<string, unknown>[]>;
    case "4":
      return api.getSubareas(sessionId);
    case "5":
      return api.getCompanies(sessionId, {}) as Promise<Record<string, unknown>[]>;
    default:
      return [];
  }
}

export function AgentDetail({
  sessionId,
  agentNum,
  agentStatus,
}: {
  sessionId: string;
  agentNum: string;
  agentStatus: Record<string, AgentStatus>;
}) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const status = agentStatus[agentNum];

  useEffect(() => {
    fetchAgentData(sessionId, agentNum)
      .then(setRows)
      .catch(() => setRows([]));
  }, [sessionId, agentNum, status]);

  const cols = rows.length ? Object.keys(rows[0]).slice(0, 8) : [];

  return (
    <Card
      title={`Agent ${agentNum} — ${AGENT_NAMES[agentNum]}`}
      action={<Badge tone={statusTone(status)}>{status ?? "Pending"}</Badge>}
    >
      {rows.length === 0 ? (
        <EmptyState
          message={`No data yet for Agent ${agentNum}.`}
          hint="Execute the pipeline from the Dashboard to populate this."
        />
      ) : (
        <div className="overflow-auto scrollbar-thin max-h-[520px] rounded-md border border-canvas-softer">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-canvas">
              <tr>
                {cols.map((c) => (
                  <th
                    key={c}
                    className="text-left px-4 py-2.5 text-[11px] uppercase tracking-wide text-body-mid font-medium border-b border-canvas-softer"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-canvas-softer/60 hover:bg-canvas-softer/60">
                  {cols.map((c) => (
                    <td key={c} className="px-4 py-2.5 text-ink-mid whitespace-nowrap">
                      {String(row[c] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
