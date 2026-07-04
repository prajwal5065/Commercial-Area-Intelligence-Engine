import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  title,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
}) {
  return (
    <div className={`bg-ink-900 border border-ink-800 rounded-xl ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-800">
          <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
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
  variant?: "primary" | "secondary" | "ghost" | "danger";
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium text-sm px-4 py-2.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-signal-500 text-ink-950 hover:bg-signal-400 font-semibold",
    secondary: "bg-ink-800 text-ink-100 border border-ink-700 hover:bg-ink-700",
    ghost: "text-ink-300 hover:text-ink-100 hover:bg-ink-800",
    danger: "bg-status-error/10 text-status-error border border-status-error/30 hover:bg-status-error/20",
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

export function StatChip({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 bg-ink-850 border border-ink-800 rounded-lg min-w-[110px]">
      <span className="font-mono text-[10px] uppercase tracking-widest text-ink-500">
        {label}
      </span>
      <span className="font-mono text-xl font-semibold text-ink-100 tabular-nums">
        {value}
      </span>
    </div>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6">
      <p className="text-sm text-ink-300">{message}</p>
      {hint && <p className="text-xs text-ink-500 mt-1">{hint}</p>}
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
      className="w-full bg-ink-850 border border-ink-700 rounded-lg px-3 py-2.5 text-sm text-ink-100 focus:border-signal-500"
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
