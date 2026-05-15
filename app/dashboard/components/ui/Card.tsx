/**
 * Card — neutral container used by every section of the dashboard.
 *
 * Two flavors:
 *   - default: white background, 1px slate border (the standard card)
 *   - subtle:  slate-50 background, no border (used for the narrative
 *              PredictionCard's inner box so it sits inside another card)
 */

import { clsx } from "clsx";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "subtle";
}

export function Card({ children, className, variant = "default" }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl",
        variant === "default" &&
          "border border-slate-200 bg-white shadow-sm",
        variant === "subtle" && "bg-slate-50",
        "px-5 py-5 sm:px-6 sm:py-6",
        className,
      )}
    >
      {children}
    </div>
  );
}
