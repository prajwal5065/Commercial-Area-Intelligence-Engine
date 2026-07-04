import { useEffect, useState } from "react";
import { api, type AgentStatus } from "../lib/api";
import { Card, EmptyState } from "../components/ui";

const AGENT_NAMES: Record<string, string> = {
  "1": "GDP Ranker",
  "2": "City Segmenter",
  "3": "Zone Finder",
  "4": "Subarea Mapper",
  "5": "Lead Scraper",
};

function statusBadgeClass(status: AgentStatus | undefined) {
  switch (status) {
    case "Done":
      return "bg-status-done/10 text-status-done border-status-done/30";
    case "Running":
      return "bg-status-running/10 text-status-running border-status-running/30";
    case "Error":
      return "bg-status-error/10 text-status-error border-status-error/30";
    default:
      return "bg-ink-800 text-ink-400 border-ink-700";
  }
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
      action={
        <span
          className={`font-mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border ${statusBadgeClass(
            status
          )}`}
        >
          {status ?? "Pending"}
        </span>
      }
    >
      {rows.length === 0 ? (
        <EmptyState
          message={`No data yet for Agent ${agentNum}.`}
          hint="Execute the pipeline from the Dashboard to populate this."
        />
      ) : (
        <div className="overflow-auto scrollbar-thin max-h-[520px] rounded-lg border border-ink-800">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink-850">
              <tr>
                {cols.map((c) => (
                  <th
                    key={c}
                    className="text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-widest text-ink-500 border-b border-ink-800"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-ink-800/60 hover:bg-ink-850/60">
                  {cols.map((c) => (
                    <td key={c} className="px-4 py-2.5 text-ink-200 whitespace-nowrap">
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
