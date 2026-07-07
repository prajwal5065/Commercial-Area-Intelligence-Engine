import type { ReactNode } from "react";

/**
 * Shared UI primitives, restyled to the Voltagent brand guide:
 * near-black canvas, electric-green accents, hairline borders on dark,
 * SF Mono / Inter typography pairing.
 */

export function Card({
  children,
  className = "",
  title,
  action,
  variant = "default",
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
  variant?: "default" | "emphasized" | "soft";
}) {
  const variants = {
    default: "bg-canvas border border-hairline shadow-md",
    emphasized: "bg-canvas border-[2px] border-hairline shadow-lg",
    soft: "bg-canvas-soft border border-hairline shadow-sm",
  };
  return (
    <div className={`rounded-xl ${variants[variant]} ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-6 py-5 border-b border-hairline">
          <h2 className="text-lg font-semibold tracking-tight text-ink font-sans">
            {title}
          </h2>
          {action}
        </div>
      )}
      <div className="p-6">{children}</div>
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
  variant?: "primary" | "outline-on-dark" | "ghost-green" | "text" | "danger";
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md font-semibold text-sm px-4 py-2.5 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed font-sans leading-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas";
  
  const variants = {
    primary: "bg-primary text-on-primary hover:bg-primary-hover shadow-sm hover:shadow-md",
    "outline-on-dark": "bg-canvas text-ink border border-hairline hover:bg-canvas-soft shadow-sm",
    "ghost-green": "bg-transparent text-primary-soft hover:text-primary hover:bg-primary-muted",
    text: "bg-transparent text-body hover:text-ink hover:bg-canvas-soft font-medium",
    danger: "bg-status-error-bg text-status-error border border-status-error/30 hover:bg-status-error/20",
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
    default: "text-ink-strong",
    running: "text-primary",
    done: "text-status-done",
    error: "text-status-error",
  }[tone];
  return (
    <div className="flex flex-col gap-1.5 px-5 py-4 bg-canvas-soft border border-hairline rounded-lg min-w-[120px] shadow-sm">
      <span className="text-xs tracking-wider text-body font-semibold font-sans uppercase">
        {label}
      </span>
      <span className={`text-3xl font-medium tabular-nums font-sans tracking-tight ${toneClass}`}>
        {value}
      </span>
    </div>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 bg-canvas-soft rounded-lg border border-dashed border-hairline-soft">
      <div className="w-12 h-12 bg-canvas border border-hairline rounded-full flex items-center justify-center mb-4 shadow-sm">
        <span className="text-body-mid text-xl">ℹ</span>
      </div>
      <p className="text-base text-ink font-medium font-sans">{message}</p>
      {hint && <p className="text-sm text-body mt-2 font-sans max-w-md">{hint}</p>}
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
      className="w-full bg-canvas-soft border border-hairline rounded-md px-4 py-2.5 text-sm text-ink font-sans focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-colors appearance-none"
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
    default: "bg-canvas text-ink border-hairline",
    running: "bg-canvas text-primary border-primary",
    done: "bg-canvas text-status-done border-status-done",
    error: "bg-canvas text-status-error border-status-error",
    pending: "bg-canvas text-body-mid border-hairline",
    warn: "bg-canvas text-status-warn border-status-warn",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 border rounded-pill text-sm font-semibold font-sans ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function ProgressBar({ value, tone = "primary" }: { value: number; tone?: "primary" | "done" | "error" }) {
  const barColor = { primary: "bg-primary", done: "bg-status-done", error: "bg-status-error" }[tone];
  return (
    <div className="w-full h-1 bg-canvas-soft rounded-pill overflow-hidden border border-hairline">
      <div
        className={`h-full rounded-pill transition-all duration-500 ${barColor}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

