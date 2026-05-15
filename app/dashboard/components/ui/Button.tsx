/**
 * Button — primary button used by the Predict action.
 *
 * Two flavors:
 *   - primary:   slate-900 fill, white text
 *   - secondary: transparent fill, slate border
 *
 * Loading state shows the spinner and disables the button. The
 * Predict button in app/page.tsx uses this with state="loading"
 * while a prediction is in flight.
 */

"use client";

import { clsx } from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { SpinnerIcon } from "./icons";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "primary" | "secondary";
  loading?: boolean;
}

export function Button({
  children,
  variant = "primary",
  loading = false,
  disabled,
  className,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      type="button"
      {...rest}
      disabled={isDisabled}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-700 focus-visible:ring-offset-2",
        variant === "primary" &&
          "bg-slate-900 text-white hover:bg-slate-800 active:bg-slate-950",
        variant === "secondary" &&
          "border border-slate-300 bg-white text-slate-900 hover:bg-slate-50",
        isDisabled && "cursor-not-allowed opacity-60 hover:bg-slate-900",
        className,
      )}
    >
      {loading && <SpinnerIcon className="text-base" aria-hidden />}
      {children}
    </button>
  );
}
