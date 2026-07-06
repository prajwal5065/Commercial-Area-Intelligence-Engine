import type { ButtonHTMLAttributes, ReactNode } from "react";

interface LandingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "default" | "outline";
  className?: string;
}

/**
 * Small local Button for the Pathfinder landing hero. The original repo's
 * Button wraps @base-ui/react/button with class-variance-authority variants;
 * since the hero only ever uses two simple variants (solid primary, ink
 * outline), a real dependency for that felt like unnecessary weight - this
 * matches the same visual result without adding @base-ui/react as a package.
 */
export function LandingButton({ children, variant = "default", className = "", ...props }: LandingButtonProps) {
  const base =
    "inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none";
  const variants = {
    default: "bg-lp-primary text-lp-primary-foreground hover:bg-lp-primary/90",
    outline: "border border-lp-border bg-lp-background text-lp-foreground hover:bg-lp-muted",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}
