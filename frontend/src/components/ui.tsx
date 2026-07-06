import type { ReactNode } from "react";

/**
 * Shared UI primitives, restyled to the Zapier brand guide:
 * warm cream canvas, deep coffee ink text, single orange accent,
 * 12px "rounded-md" as the canonical radius for buttons + cards,
 * 1px ink hairline border as the default card elevation (guide's
 * "Level 1 — Hairline" treatment) rather than a shadow.
 */

export function Card({
  children,
  className = "",
  title,
  action,
  variant = "cream",
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
  variant?: "cream" | "dark" | "outline";
}) {
  const variants = {
    cream: "bg-canvas-soft border border-canvas-softer",
    dark: "bg-ink text-canvas-soft border border-ink",
    outline: "bg-canvas border border-ink",
  };
  return (
    <div className={`rounded-md ${variants[variant]} ${className}`}>
      {title && (
        <div className={`flex items-center justify-between px-5 py-4 border-b ${variant === "dark" ? "border-ink-soft" : "border-canvas-softer"}`}>
          <h2 className={`text-[15px] font-semibold tracking-tight ${variant === "dark" ? "text-canvas-soft" : "text-ink"}`}>
            {title}
          </h2>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "tertiary" | "text" | "danger";
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md font-semibold text-sm px-4 py-2.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    // button-primary: orange fill, warm-white text
    primary: "bg-primary text-on-primary hover:bg-primary-hover",
    // button-secondary: dark coffee-ink fill
    secondary: "bg-ink text-canvas-soft hover:bg-ink-soft",
    // button-tertiary: outline, ink border on cream
    tertiary: "bg-canvas text-ink border border-ink hover:bg-canvas-soft",
    // button-text: text-only, used inside cards/nav
    text: "bg-transparent text-ink hover:bg-canvas-softer font-medium",
    danger: "bg-status-error-bg text-status-error border border-status-error/30 hover:bg-status-error/10",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function StatChip({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number | string;
  tone?: "default" | "running" | "done" | "error";
}) {
  const toneClass = {
    default: "text-ink",
    running: "text-primary",
    done: "text-status-done",
    error: "text-status-error",
  }[tone];
  return (
    <div className="flex flex-col gap-1 px-4 py-3 bg-canvas border border-canvas-softer rounded-md min-w-[120px]">
      <span className="text-[11px] uppercase tracking-wide text-body-mid font-medium">
        {label}
      </span>
      <span className={`text-2xl font-semibold tabular-nums ${toneClass}`} style={{ fontFamily: "var(--font-display)" }}>
        {value}
      </span>
    </div>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6">
      <p className="text-sm text-body">{message}</p>
      {hint && <p className="text-xs text-body-mid mt-1">{hint}</p>}
    </div>
  );
}

export function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-canvas border border-ink rounded-sm px-3 py-2.5 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/40"
    >
      <option value="">{placeholder ?? "-- select --"}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "running" | "done" | "error" | "pending" | "warn";
}) {
  const tones = {
    default: "bg-canvas-softer text-ink",
    running: "bg-primary/10 text-primary",
    done: "bg-status-done-bg text-status-done",
    error: "bg-status-error-bg text-status-error",
    pending: "bg-canvas-softer text-body-mid",
    warn: "bg-status-warn-bg text-status-warn",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function ProgressBar({ value, tone = "primary" }: { value: number; tone?: "primary" | "done" | "error" }) {
  const barColor = { primary: "bg-primary", done: "bg-status-done", error: "bg-status-error" }[tone];
  return (
    <div className="w-full h-1.5 bg-canvas-softer rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${barColor}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}
