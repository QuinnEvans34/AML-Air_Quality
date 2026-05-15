/**
 * PredictionCard — the hero outlook card.
 *
 * Visual language: big verdict icon on the left, narrative content on
 * the right, semantic color tone across the whole card. Inspired by
 * iOS Weather's "current conditions" card.
 */

"use client";

import { clsx } from "clsx";
import {
  AlertOctagon,
  AlertTriangle,
  CloudSun,
  Info,
  Loader2,
  Sparkles,
  Sun,
  ThumbsUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { PlainLanguageVerdict } from "@/lib/types";

interface PredictionCardProps {
  state: "empty" | "loading" | "result" | "error";
  verdict?: PlainLanguageVerdict | null;
  errorMessage?: string | null;
  unsafeHours?: number;
  totalHours?: number;
}

const CONFIDENCE_LABEL: Record<"high" | "medium" | "low", string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

const CONFIDENCE_PERCENT: Record<"high" | "medium" | "low", number> = {
  high: 95,
  medium: 65,
  low: 35,
};

interface Visual {
  Icon: LucideIcon;
  tint: string;
  iconBg: string;
  iconColor: string;
  cardBg: string;
  border: string;
  accent: string;
  label: string;
}

function visualFor(verdict: PlainLanguageVerdict): Visual {
  if (!verdict.any_unsafe) {
    return {
      Icon: Sun,
      tint: "safe",
      iconBg: "bg-safe-100",
      iconColor: "text-safe-700",
      cardBg: "bg-gradient-to-br from-safe-50 to-white",
      border: "border-safe-200",
      accent: "text-safe-700",
      label: "Safe",
    };
  }
  // Pick severity from confidence — "high confidence unsafe" gets the
  // sharpest icon; medium gets a softer warning.
  if (verdict.confidence === "high") {
    return {
      Icon: AlertOctagon,
      tint: "unsafe",
      iconBg: "bg-unsafe-100",
      iconColor: "text-unsafe-700",
      cardBg: "bg-gradient-to-br from-unsafe-50 to-white",
      border: "border-unsafe-200",
      accent: "text-unsafe-700",
      label: "Unsafe",
    };
  }
  return {
    Icon: AlertTriangle,
    tint: "caution",
    iconBg: "bg-caution-100",
    iconColor: "text-caution-700",
    cardBg: "bg-gradient-to-br from-caution-50 to-white",
    border: "border-caution-200",
    accent: "text-caution-700",
    label: "Caution",
  };
}

export function PredictionCard({
  state,
  verdict,
  errorMessage,
  unsafeHours,
  totalHours,
}: PredictionCardProps) {
  if (state === "empty") {
    return (
      <div className="flex h-full flex-col items-start justify-center rounded-3xl border border-slate-200 bg-white px-7 py-8 shadow-soft">
        <div className="rounded-2xl bg-brand-50 p-3">
          <Sparkles className="h-6 w-6 text-brand-600" aria-hidden />
        </div>
        <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Ready
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
          Pick a location and time
        </h2>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-600">
          AirAlert will look at the last 30 days of measurements, build the
          hourly features the model expects, and predict whether the air is
          likely to be safe for outdoor recess.
        </p>
      </div>
    );
  }

  if (state === "loading") {
    return (
      <div className="flex h-full flex-col items-start justify-center rounded-3xl border border-slate-200 bg-white px-7 py-8 shadow-soft">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          <span>Building features and running predictions…</span>
        </div>
        <div className="mt-5 h-7 w-3/4 animate-pulse rounded-md bg-slate-100" />
        <div className="mt-3 h-5 w-2/3 animate-pulse rounded-md bg-slate-100" />
        <div className="mt-4 h-2 w-full animate-pulse rounded-full bg-slate-100" />
      </div>
    );
  }

  if (state === "error") {
    return (
      <div
        role="alert"
        className="flex h-full flex-col items-start justify-center rounded-3xl border border-unsafe-200 bg-gradient-to-br from-unsafe-50 to-white px-7 py-8 shadow-soft"
      >
        <div className="rounded-2xl bg-unsafe-100 p-3">
          <AlertOctagon className="h-6 w-6 text-unsafe-700" aria-hidden />
        </div>
        <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-unsafe-700">
          Something went wrong
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
          We couldn&apos;t make a prediction.
        </h2>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-600">
          {errorMessage ??
            "Try a different location or date. If this keeps happening, check that the model has been trained recently."}
        </p>
      </div>
    );
  }

  if (!verdict) return null;
  const v = visualFor(verdict);
  const VerdictIcon = v.Icon;
  const RecIcon = verdict.any_unsafe ? CloudSun : ThumbsUp;
  const confidencePct = CONFIDENCE_PERCENT[verdict.confidence];

  return (
    <div
      role="status"
      aria-live="polite"
      className={clsx(
        "flex h-full flex-col rounded-3xl border px-7 py-8 shadow-soft animate-fade-in",
        v.cardBg,
        v.border,
      )}
    >
      <div className="flex items-start gap-5">
        <div
          className={clsx(
            "flex-shrink-0 rounded-2xl p-3.5",
            v.iconBg,
          )}
        >
          <VerdictIcon className={clsx("h-8 w-8", v.iconColor)} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p
            className={clsx(
              "text-xs font-semibold uppercase tracking-wider",
              v.accent,
            )}
          >
            Outlook · {v.label}
          </p>
          <h2 className="mt-1 text-2xl font-semibold leading-tight tracking-tight text-slate-900">
            {renderHeadlineWithColoredVerdict(verdict, v.accent)}
          </h2>
          <p className="mt-2 flex items-center gap-2 text-base leading-relaxed text-slate-700">
            <RecIcon className="h-4 w-4 text-slate-500" aria-hidden />
            <span>{verdict.recommendation}</span>
          </p>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mt-6">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {CONFIDENCE_LABEL[verdict.confidence]}
          </span>
          {typeof unsafeHours === "number" && typeof totalHours === "number" && (
            <span className="text-xs tabular-nums text-slate-600">
              {unsafeHours} of {totalHours} hours predicted unsafe
            </span>
          )}
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className={clsx(
              "h-full rounded-full transition-all duration-500",
              verdict.confidence === "high" && "bg-slate-900",
              verdict.confidence === "medium" && "bg-caution-500",
              verdict.confidence === "low" && "bg-slate-400",
            )}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      <div className="mt-5 flex items-start gap-2 rounded-2xl bg-white/60 px-3.5 py-2.5 text-xs leading-relaxed text-slate-600">
        <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-slate-400" aria-hidden />
        <span>
          Confidence reflects the model&apos;s probability bucket
          (high ≥ 0.70, medium ≥ 0.40, low &lt; 0.40). Probabilities are
          a relative ranking, not a calibrated chance.
        </span>
      </div>
    </div>
  );
}

function renderHeadlineWithColoredVerdict(
  verdict: PlainLanguageVerdict,
  accentClass: string,
) {
  const text = verdict.headline;
  const keyword = verdict.any_unsafe ? "UNSAFE" : "SAFE";
  const idx = text.indexOf(keyword);
  if (idx === -1) return <span>{text}</span>;
  const periodIdx = text.indexOf(".", idx);
  const phraseEnd = periodIdx === -1 ? text.length : periodIdx;
  const before = text.slice(0, idx);
  const phrase = text.slice(idx, phraseEnd);
  const after = text.slice(phraseEnd);
  return (
    <>
      {before}
      <span className={clsx("font-bold", accentClass)}>{phrase}</span>
      {after}
    </>
  );
}
