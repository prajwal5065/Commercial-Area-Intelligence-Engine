import { useState, type KeyboardEvent } from "react";
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
  /**
   * When true, Name mode accepts free-typed values (press Enter/comma to add
   * a tag) instead of requiring a pre-existing options list. Used for Stage 1
   * (Countries), where there's no backend list to check boxes against until
   * this very stage runs - so users type country names directly instead.
   */
  allowFreeText?: boolean;
}

/**
 * Lets the user configure one pipeline stage (countries / cities / zones /
 * sub-areas) either by a count ("Top N") or by explicitly picking named
 * items - via a multi-select checkbox dropdown when a backend options list
 * exists, or via a free-text tag input when it doesn't (allowFreeText).
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
  allowFreeText,
}: StageConfiguratorProps) {
  const [mode, setMode] = useState<StageMode>("number");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [tagDraft, setTagDraft] = useState("");

  const useFreeText = allowFreeText && nameOptions.length === 0;

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

  function commitTagDraft() {
    const value = tagDraft.trim();
    if (value && !selectedNames.some((n) => n.toLowerCase() === value.toLowerCase())) {
      onSelectedNamesChange([...selectedNames, value]);
    }
    setTagDraft("");
  }

  function handleTagKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commitTagDraft();
    } else if (e.key === "Backspace" && tagDraft === "" && selectedNames.length > 0) {
      onSelectedNamesChange(selectedNames.slice(0, -1));
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <label className="font-mono text-[11px] font-semibold tracking-[2.52px] uppercase text-body">
          {label}
        </label>
        <div className="flex items-center rounded-lg bg-canvas border border-hairline p-0.5">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setMode("number")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-40 ${
              mode === "number"
                ? "bg-primary text-on-primary"
                : "text-body-mid hover:text-ink"
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
                ? "bg-primary text-on-primary"
                : "text-body-mid hover:text-ink"
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
          className="w-full bg-canvas border border-hairline rounded-lg px-3 py-2.5 text-sm text-ink focus:border-primary focus:outline-none disabled:opacity-40"
        />
      ) : useFreeText ? (
        <div
          className={`w-full flex flex-wrap items-center gap-1.5 bg-canvas border rounded-lg px-2.5 py-2 focus-within:border-primary ${
            disabled ? "border-hairline opacity-40" : "border-hairline"
          }`}
        >
          {selectedNames.map((n) => (
            <span
              key={n}
              className="inline-flex items-center gap-1 bg-primary/10 border border-primary/30 text-primary text-xs rounded-full pl-2.5 pr-1.5 py-1"
            >
              {n}
              <button
                type="button"
                onClick={() => toggleName(n)}
                disabled={disabled}
                className="hover:text-primary-hover"
                aria-label={`Remove ${n}`}
              >
                ×
              </button>
            </span>
          ))}
          <input
            value={tagDraft}
            onChange={(e) => setTagDraft(e.target.value)}
            onKeyDown={handleTagKeyDown}
            onBlur={commitTagDraft}
            disabled={disabled}
            placeholder={selectedNames.length === 0 ? "Type a name, press Enter…" : "Add another…"}
            className="flex-1 min-w-[120px] bg-transparent text-sm text-ink placeholder-ink-500 focus:outline-none py-1 disabled:cursor-not-allowed"
          />
        </div>
      ) : (
        <div className="relative">
          <button
            type="button"
            disabled={disabled || nameOptions.length === 0}
            onClick={() => setDropdownOpen((v) => !v)}
            className="w-full flex items-center justify-between gap-2 bg-canvas border border-hairline rounded-lg px-3 py-2.5 text-sm text-left text-ink focus:border-primary focus:outline-none disabled:opacity-40"
          >
            <span className="truncate text-ink">
              {nameOptions.length === 0
                ? "No options yet — run the previous stage first"
                : selectedNames.length === 0
                ? "All (none selected)"
                : selectedNames.length <= 2
                ? selectedNames.join(", ")
                : `${selectedNames.length} selected`}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-body-mid shrink-0" />
          </button>

          {dropdownOpen && (
            <div className="absolute z-20 mt-1.5 w-full bg-canvas border border-hairline rounded-lg shadow-xl shadow-black/40 overflow-hidden">
              <div className="p-2 border-b border-hairline">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search…"
                  autoFocus
                  className="w-full bg-canvas-soft border border-hairline rounded-md px-2.5 py-1.5 text-xs text-ink focus:border-primary focus:outline-none"
                />
              </div>
              <div className="max-h-56 overflow-auto scrollbar-thin">
                {filteredOptions.length === 0 ? (
                  <p className="px-3 py-2.5 text-xs text-body-mid">No matches.</p>
                ) : (
                  filteredOptions.map((opt) => (
                    <label
                      key={opt}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-ink hover:bg-canvas-soft cursor-pointer"
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
              <div className="flex items-center justify-between px-3 py-2 border-t border-hairline">
                <button
                  type="button"
                  onClick={() => onSelectedNamesChange([])}
                  className="text-xs text-body-mid hover:text-body"
                >
                  Clear
                </button>
                <button
                  type="button"
                  onClick={() => setDropdownOpen(false)}
                  className="text-xs font-medium text-primary hover:text-primary"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {mode === "name" && !useFreeText && selectedNames.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedNames.map((n) => (
            <span
              key={n}
              className="inline-flex items-center gap-1 bg-primary/10 border border-primary/30 text-primary text-xs rounded-full px-2.5 py-1"
            >
              {n}
              <button
                type="button"
                onClick={() => toggleName(n)}
                className="hover:text-primary-hover"
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
