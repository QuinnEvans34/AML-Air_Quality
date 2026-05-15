/**
 * PredictButton — primary call-to-action with Sparkles icon + arrow.
 */

"use client";

import { clsx } from "clsx";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";

interface PredictButtonProps {
  state: "default" | "loading" | "disabled";
  onClick: () => void;
}

export function PredictButton({ state, onClick }: PredictButtonProps) {
  const isLoading = state === "loading";
  const isDisabled = state === "disabled" || isLoading;

  return (
    <button
      type="submit"
      onClick={onClick}
      disabled={isDisabled}
      className={clsx(
        "group relative inline-flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
        isDisabled
          ? "cursor-not-allowed bg-slate-200 text-slate-500"
          : "bg-brand-600 text-white shadow-soft hover:bg-brand-700 active:scale-[0.98]",
      )}
    >
      {isLoading ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          <span>Predicting…</span>
        </>
      ) : (
        <>
          <Sparkles className="h-4 w-4" aria-hidden />
          <span>Get prediction</span>
          <ArrowRight
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </>
      )}
    </button>
  );
}
