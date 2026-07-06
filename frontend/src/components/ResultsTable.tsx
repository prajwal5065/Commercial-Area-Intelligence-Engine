import { EmptyState } from "./ui";

const STANDARD_COLS = [
  "company_name",
  "category",
  "priority",
  "subarea_name",
  "zone_name",
  "city_name",
  "country_name",
];

const COL_LABELS: Record<string, string> = {
  company_name: "Company",
  category: "Category",
  priority: "Priority",
  subarea_name: "Sub-area",
  zone_name: "Zone",
  city_name: "City",
  country_name: "Country",
};

export function ResultsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        message="No company data yet."
        hint="Results will appear here once the lead scraper (Agent 5) completes."
      />
    );
  }

  const cols = STANDARD_COLS.filter((c) => c in rows[0]);

  return (
    <div className="overflow-auto scrollbar-thin max-h-[420px] rounded-lg border border-canvas-softer">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-canvas">
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                className="text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-widest text-body-mid border-b border-canvas-softer"
              >
                {COL_LABELS[c] ?? c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-canvas-softer/60 hover:bg-canvas/60">
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
  );
}
