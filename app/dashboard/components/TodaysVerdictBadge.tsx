/**
 * TodaysVerdictBadge — one-glance GO / MONITOR / HOLD / INDOORS pill.
 *
 * The single most useful thing for a K-5 principal at 8 AM is a giant
 * tinted card telling them what to do with recess today. Renders only
 * when there's a result; empty / loading / error states are handled
 * by the PredictionCard.
 */

"use client";

import { clsx } from "clsx";
import {
  AlertOctagon,
  AlertTriangle,
  Eye,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { schoolPeriodFor } from "@/lib/plainLanguage";
import { utcHourToMtHour } from "@/lib/timezone";
import type { HourlyPrediction } from "@/lib/types";

type VerdictTier = "go" | "monitor" | "hold" | "indoors";

interface TierVisual {
  Icon: LucideIcon;
  cardBg: string;
  border: string;
  accent: string;
  iconBg: string;
  iconColor: string;
}

const TIER_VISUALS: Record<VerdictTier, TierVisual> = {
  go: {
    Icon: ShieldCheck,
    cardBg: "bg-gradient-to-br from-safe-50 to-white",
    border: "border-safe-200",
    accent: "text-safe-700",
    iconBg: "bg-safe-100",
    iconColor: "text-safe-700",
  },
  monitor: {
    Icon: Eye,
    cardBg: "bg-gradient-to-br from-caution-50 to-white",
    border: "border-caution-200",
    accent: "text-caution-700",
    iconBg: "bg-caution-100",
    iconColor: "text-caution-700",
  },
  hold: {
    Icon: AlertTriangle,
    cardBg: "bg-gradient-to-br from-caution-50 to-white",
    border: "border-caution-200",
    accent: "text-caution-700",
    iconBg: "bg-caution-100",
    iconColor: "text-caution-700",
  },
  indoors: {
    Icon: AlertOctagon,
    cardBg: "bg-gradient-to-br from-unsafe-50 to-white",
    border: "border-unsafe-200",
    accent: "text-unsafe-700",
    iconBg: "bg-unsafe-100",
    iconColor: "text-unsafe-700",
  },
};

interface VerdictPayload {
  tier: VerdictTier;
  headline: string;
  sub: string;
}

function todaysVerdictTier(predictions: HourlyPrediction[]): VerdictPayload {
  const totalCount = predictions.length;
  const unsafeCount = predictions.filter((p) => p.is_unsafe === 1).length;

  const coreUnsafe = predictions.filter((p) => {
    if (p.is_unsafe !== 1) return false;
    const { hour } = utcHourToMtHour(p.hour_of_day, p.timestamp.slice(0, 10));
    return schoolPeriodFor(hour) === "core";
  }).length;
  const afterUnsafe = predictions.filter((p) => {
    if (p.is_unsafe !== 1) return false;
    const { hour } = utcHourToMtHour(p.hour_of_day, p.timestamp.slice(0, 10));
    return schoolPeriodFor(hour) === "after_school";
  }).length;

  if (unsafeCount === 0) {
    return {
      tier: "go",
      headline: "GO",
      sub: `Outdoor recess is clear across all ${totalCount} hours.`,
    };
  }
  if (coreUnsafe === 0 && afterUnsafe > 0) {
    return {
      tier: "monitor",
      headline: "MONITOR",
      sub: `Recess is clear; ${afterUnsafe} after-school hour${afterUnsafe > 1 ? "s" : ""} need watching.`,
    };
  }
  if (coreUnsafe >= Math.ceil(totalCount * 0.5)) {
    return {
      tier: "indoors",
      headline: "INDOORS",
      sub: `${coreUnsafe} of the recess hours predicted unsafe. Plan an indoor day.`,
    };
  }
  return {
    tier: "hold",
    headline: "HOLD",
    sub: `${coreUnsafe} recess hour${coreUnsafe > 1 ? "s" : ""} predicted unsafe. Watch the strip below.`,
  };
}

interface TodaysVerdictBadgeProps {
  predictions: HourlyPrediction[];
}

export function TodaysVerdictBadge({ predictions }: TodaysVerdictBadgeProps) {
  if (predictions.length === 0) return null;
  const { tier, headline, sub } = todaysVerdictTier(predictions);
  const visual = TIER_VISUALS[tier];
  const Icon = visual.Icon;

  return (
    <div
      role="status"
      aria-live="polite"
      className={clsx(
        "flex items-center gap-5 rounded-3xl border px-6 py-6 shadow-soft animate-fade-in sm:px-8",
        visual.cardBg,
        visual.border,
      )}
    >
      <div className={clsx("flex-shrink-0 rounded-2xl p-4", visual.iconBg)}>
        <Icon className={clsx("h-10 w-10", visual.iconColor)} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={clsx(
            "text-xs font-semibold uppercase tracking-wider",
            visual.accent,
          )}
        >
          Today&apos;s call
        </p>
        <p
          className={clsx(
            "mt-1 text-5xl font-black tracking-tight sm:text-6xl",
            visual.accent,
          )}
        >
          {headline}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-slate-700 sm:text-base">
          {sub}
        </p>
      </div>
    </div>
  );
}
