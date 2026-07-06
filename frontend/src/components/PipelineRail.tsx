import { Check, Loader2, AlertTriangle, Circle } from "lucide-react";
import type { AgentStatus } from "../lib/api";

export interface RailAgent {
  num: string;
  short: string;
  label: string;
}

const AGENTS: RailAgent[] = [
  { num: "1", short: "GDP", label: "GDP Ranker" },
  { num: "2", short: "CITY", label: "City Segmenter" },
  { num: "3", short: "ZONE", label: "Zone Finder" },
  { num: "4", short: "SUB", label: "Subarea Mapper" },
  { num: "5", short: "LEAD", label: "Lead Scraper" },
];

function StatusIcon({ status }: { status: AgentStatus | undefined }) {
  switch (status) {
    case "Done":
      return <Check className="w-3.5 h-3.5" strokeWidth={3} />;
    case "Running":
      return <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={3} />;
    case "Error":
      return <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2.5} />;
    default:
      return <Circle className="w-2 h-2 fill-current" />;
  }
}

function statusColor(status: AgentStatus | undefined) {
  switch (status) {
    case "Done":
      return "text-status-done border-status-done bg-status-done-bg";
    case "Running":
      return "text-primary border-primary bg-primary/10";
    case "Error":
      return "text-status-error border-status-error bg-status-error-bg";
    default:
      return "text-body-mid border-hairline bg-canvas";
  }
}

interface PipelineRailProps {
  agentStatus: Record<string, AgentStatus>;
  activeAgent: string;
  onSelectAgent: (num: string) => void;
}

/**
 * Vertical rail encoding the real dependency chain of the pipeline:
 * Agent 2 can't run until Agent 1 is Done, and so on. This is a genuine
 * sequence (not a decorative numbered list) - order carries information
 * about what's runnable right now.
 */
export function PipelineRail({ agentStatus, activeAgent, onSelectAgent }: PipelineRailProps) {
  return (
    <nav className="flex flex-col" aria-label="Pipeline stages">
      {AGENTS.map((agent, i) => {
        const status = agentStatus[agent.num];
        const isActive = activeAgent === agent.num;
        const isLast = i === AGENTS.length - 1;
        return (
          <div key={agent.num} className="flex flex-col">
            <button
              onClick={() => onSelectAgent(agent.num)}
              className={`group flex items-center gap-3 px-4 py-3 text-left rounded-sm transition-colors ${
                isActive ? "bg-canvas-soft" : "hover:bg-canvas-soft"
              }`}
              aria-current={isActive ? "step" : undefined}
            >
              <span
                className={`flex items-center justify-center w-7 h-7 rounded-full border shrink-0 ${statusColor(
                  status
                )}`}
              >
                <StatusIcon status={status} />
              </span>
              <span className="flex flex-col min-w-0">
                <span
                  className={`font-mono text-xs uppercase tracking-widest ${
                    isActive ? "text-primary" : "text-body-mid"
                  }`}
                >
                  Agent {agent.num} · {agent.short}
                </span>
                <span
                  className={`text-sm font-medium truncate font-sans ${
                    isActive ? "text-ink-strong" : "text-body"
                  }`}
                >
                  {agent.label}
                </span>
              </span>
            </button>
            {!isLast && (
              <div className="ml-[1.9rem] w-px h-3 bg-hairline" aria-hidden="true" />
            )}
          </div>
        );
      })}
    </nav>
  );
}
