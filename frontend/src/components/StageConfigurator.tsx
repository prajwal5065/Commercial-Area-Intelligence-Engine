import { useState } from "react";
import { Hash, ListChecks, ChevronDown } from "lucide-react";

export type StageMode = "number" | "name";

interface StageConfiguratorProps {
  label: string;
  numberLabel: string;
  numberValue: string;
  onNumberChange: (v: string) => void;
  nameOptions: string[];
  selectedNames: string[];
  onSelectedNamesChange: (v: string[]) => void;
  disabled?: boolean;
}

/**
 * Lets the user configure one pipeline stage (countries / cities / zones /
 * sub-areas) either by a count ("Top N") or by explicitly picking named
 * items via a multi-select checkbox dropdown (e.g. India, USA, Japan).
 *
 * Maps directly onto the existing backend contract: Agent endpoints already
 * accept either `top_n` or a `selected_*` list - this only changes how the
 * frontend collects that input.
 */
export function StageConfigurator({
  label,
  numberLabel,
  numberValue,
  onNumberChange,
  nameOptions,
  selectedNames,
  onSelectedNamesChange,
  disabled,
}: StageConfiguratorProps) {
  const [mode, setMode] = useState<StageMode>("number");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [search, setSearch] = useState("");

  const filteredOptions = nameOptions.filter((o) =>
    o.toLowerCase().includes(search.toLowerCase())
  );

  function toggleName(name: string) {
    if (selectedNames.includes(name)) {
      onSelectedNamesChange(selectedNames.filter((n) => n !== name));
    } else {
      onSelectedNamesChange([...selectedNames, name]);
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <label className="font-mono text-[10px] uppercase tracking-widest text-ink-500">
          {label}
        </label>
        <div className="flex items-center rounded-lg bg-ink-850 border border-ink-700 p-0.5">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setMode("number")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-40 ${
              mode === "number"
                ? "bg-signal-500 text-ink-950"
                : "text-ink-400 hover:text-ink-200"
            }`}
          >
            <Hash className="w-3 h-3" />
            Number
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setMode("name")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-40 ${
              mode === "name"
                ? "bg-signal-500 text-ink-950"
                : "text-ink-400 hover:text-ink-200"
            }`}
          >
            <ListChecks className="w-3 h-3" />
            Name
          </button>
        </div>
      </div>

      {mode === "number" ? (
        <input
          value={numberValue}
          onChange={(e) => onNumberChange(e.target.value)}
          disabled={disabled}
          placeholder={numberLabel}
          className="w-full bg-ink-850 border border-ink-700 rounded-lg px-3 py-2.5 text-sm text-ink-100 focus:border-signal-500 focus:outline-none disabled:opacity-40"
        />
      ) : (
        <div className="relative">
          <button
            type="button"
            disabled={disabled || nameOptions.length === 0}
            onClick={() => setDropdownOpen((v) => !v)}
            className="w-full flex items-center justify-between gap-2 bg-ink-850 border border-ink-700 rounded-lg px-3 py-2.5 text-sm text-left text-ink-100 focus:border-signal-500 focus:outline-none disabled:opacity-40"
          >
            <span className="truncate text-ink-200">
              {nameOptions.length === 0
                ? "No options yet — run the previous stage first"
                : selectedNames.length === 0
                ? "All (none selected)"
                : selectedNames.length <= 2
                ? selectedNames.join(", ")
                : `${selectedNames.length} selected`}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-ink-500 shrink-0" />
          </button>

          {dropdownOpen && (
            <div className="absolute z-20 mt-1.5 w-full bg-ink-850 border border-ink-700 rounded-lg shadow-xl shadow-black/40 overflow-hidden">
              <div className="p-2 border-b border-ink-700">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search…"
                  autoFocus
                  className="w-full bg-ink-900 border border-ink-700 rounded-md px-2.5 py-1.5 text-xs text-ink-100 focus:border-signal-500 focus:outline-none"
                />
              </div>
              <div className="max-h-56 overflow-auto scrollbar-thin">
                {filteredOptions.length === 0 ? (
                  <p className="px-3 py-2.5 text-xs text-ink-500">No matches.</p>
                ) : (
                  filteredOptions.map((opt) => (
                    <label
                      key={opt}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-ink-200 hover:bg-ink-800 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedNames.includes(opt)}
                        onChange={() => toggleName(opt)}
                        className="w-3.5 h-3.5 accent-signal-500 shrink-0"
                      />
                      <span className="truncate">{opt}</span>
                    </label>
                  ))
                )}
              </div>
              <div className="flex items-center justify-between px-3 py-2 border-t border-ink-700">
                <button
                  type="button"
                  onClick={() => onSelectedNamesChange([])}
                  className="text-xs text-ink-500 hover:text-ink-300"
                >
                  Clear
                </button>
                <button
                  type="button"
                  onClick={() => setDropdownOpen(false)}
                  className="text-xs font-medium text-signal-400 hover:text-signal-300"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {mode === "name" && selectedNames.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedNames.map((n) => (
            <span
              key={n}
              className="inline-flex items-center gap-1 bg-signal-500/10 border border-signal-500/30 text-signal-400 text-xs rounded-full px-2.5 py-1"
            >
              {n}
              <button
                type="button"
                onClick={() => toggleName(n)}
                className="hover:text-signal-200"
                aria-label={`Remove ${n}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
