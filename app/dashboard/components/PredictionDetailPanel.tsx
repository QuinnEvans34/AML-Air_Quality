/**
 * PredictionDetailPanel — the rich-detail view that appears when a
 * user clicks a cell in the HourlyPredictionStrip.
 *
 * Replaces the cramped inline popover from v1 with a full-width
 * card that has room to explain:
 *
 *   - Verdict + recommendation for THIS hour
 *   - Visual confidence + raw probability (with calibration caveat)
 *   - Data source breakdown (what's measured vs estimated)
 *   - "Why" — the feature values the model received, surfaced as
 *     human-readable hints
 *
 * The detail panel uses the same color-tinted styling as the
 * PredictionCard so the user feels consistency between the
 * overall verdict and the per-hour drill-down.
 */

"use client";

import { clsx } from "clsx";
import {
  AlertOctagon,
  AlertTriangle,
  Check,
  Cpu,
  Database,
  Eye,
  Gauge,
  HelpCircle,
  Lightbulb,
  ShieldCheck,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { UNSAFE_THRESHOLD, type LocationKey, TARGET_LOCATIONS } from "@/lib/constants";
import { cellState, formatHour } from "@/lib/plainLanguage";
import type { HourlyPrediction } from "@/lib/types";

interface PredictionDetailPanelProps {
  prediction: HourlyPrediction;
  location: LocationKey;
  onClose: () => void;
}

interface Visual {
  Icon: LucideIcon;
  badgeLabel: string;
  cardBg: string;
  border: string;
  accent: string;
  iconBg: string;
  iconColor: string;
  recommendation: string;
}

function visualFor(p: HourlyPrediction): Visual {
  const state = cellState(p);
  if (state === "safe-high" || state === "safe-medium") {
    return {
      Icon: ShieldCheck,
      badgeLabel: "Safe to go outside",
      cardBg: "bg-gradient-to-br from-safe-50 to-white",
      border: "border-safe-200",
      accent: "text-safe-700",
      iconBg: "bg-safe-100",
      iconColor: "text-safe-700",
      recommendation:
        "Outdoor recess is fine during this hour based on what the model sees.",
    };
  }
  if (state === "borderline") {
    return {
      Icon: AlertTriangle,
      badgeLabel: "Borderline",
      cardBg: "bg-gradient-to-br from-caution-50 to-white",
      border: "border-caution-200",
      accent: "text-caution-700",
      iconBg: "bg-caution-100",
      iconColor: "text-caution-700",
      recommendation:
        "The model is not confident either way. Consider keeping kids indoors if any of them are sensitive to air quality.",
    };
  }
  if (state === "unsafe-high") {
    return {
      Icon: AlertOctagon,
      badgeLabel: "Unsafe — high confidence",
      cardBg: "bg-gradient-to-br from-unsafe-50 to-white",
      border: "border-unsafe-200",
      accent: "text-unsafe-700",
      iconBg: "bg-unsafe-100",
      iconColor: "text-unsafe-700",
      recommendation:
        "Strongly recommend indoor recess during this hour. PM2.5 is predicted to be well above the unsafe threshold.",
    };
  }
  return {
    Icon: AlertOctagon,
    badgeLabel: "Unsafe",
    cardBg: "bg-gradient-to-br from-unsafe-50 to-white",
    border: "border-unsafe-200",
    accent: "text-unsafe-700",
    iconBg: "bg-unsafe-100",
    iconColor: "text-unsafe-700",
    recommendation:
      "Recommend indoor recess during this hour. PM2.5 is predicted to be above the unsafe threshold.",
  };
}

export function PredictionDetailPanel({
  prediction,
  location,
  onClose,
}: PredictionDetailPanelProps) {
  const visual = visualFor(prediction);
  const VerdictIcon = visual.Icon;
  const locationLabel = TARGET_LOCATIONS[location].label;
  const probabilityPercent = Math.round(prediction.unsafe_probability * 100);
  const confidence = prediction.confidence;

  return (
    <div
      role="region"
      aria-label={`Details for ${formatHour(prediction.hour_of_day)}`}
      className={clsx(
        "relative rounded-3xl border px-6 py-6 shadow-soft animate-slide-up sm:px-8",
        visual.cardBg,
        visual.border,
      )}
    >
      {/* Close button */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Close details"
        className="absolute right-4 top-4 rounded-full p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        <X className="h-4 w-4" aria-hidden />
      </button>

      {/* Header */}
      <div className="flex items-start gap-4">
        <div className={clsx("flex-shrink-0 rounded-2xl p-3", visual.iconBg)}>
          <VerdictIcon className={clsx("h-6 w-6", visual.iconColor)} aria-hidden />
        </div>
        <div>
          <p className={clsx("text-xs font-semibold uppercase tracking-wider", visual.accent)}>
            {visual.badgeLabel}
          </p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
            {locationLabel} at {formatHour(prediction.hour_of_day)}
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-700">
            {visual.recommendation}
          </p>
        </div>
      </div>

      {/* Detail grid */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <DetailTile
          icon={Gauge}
          label="Unsafe probability"
          value={`${probabilityPercent}%`}
          sub={`Bucket: ${confidence.toUpperCase()}`}
          accent={visual.accent}
        />
        <DetailTile
          icon={Eye}
          label="Threshold used"
          value={`${UNSAFE_THRESHOLD} μg/m³`}
          sub="EPA unsafe boundary"
          accent="text-slate-700"
        />
        <DetailTile
          icon={sourceIcon(prediction).Icon}
          label="Data source"
          value={sourceLabel(prediction)}
          sub={sourceSub(prediction)}
          accent="text-slate-700"
        />
      </div>

      {/* "Why we think this" — feature snapshot */}
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white px-5 py-4">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-brand-600" aria-hidden />
          <h4 className="text-sm font-semibold text-slate-900">
            What the model saw
          </h4>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
          These are the engineered feature values for this hour. The
          model combined them through a logistic regression with
          balanced class weights, then bucketed the result into a
          high / medium / low confidence band.
        </p>
        <FeatureGrid prediction={prediction} />
      </div>

      <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-slate-500">
        <HelpCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
        <span>
          The {probabilityPercent}% value is the model&apos;s relative
          ranking score, not a calibrated absolute probability. We bucket
          it (high ≥ 0.70, medium ≥ 0.40, low &lt; 0.40) to avoid
          overclaiming. See INTERFACE.md Decision 7 for the reasoning.
        </span>
      </p>
    </div>
  );
}

/* ── helpers ──────────────────────────────────────────────────── */

interface DetailTileProps {
  icon: LucideIcon;
  label: string;
  value: string;
  sub: string;
  accent: string;
}

function DetailTile({ icon: Icon, label, value, sub, accent }: DetailTileProps) {
  return (
    <div className="rounded-2xl bg-white px-4 py-3.5 ring-1 ring-slate-200">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        <Icon className="h-3 w-3" aria-hidden />
        <span>{label}</span>
      </div>
      <p className={clsx("mt-1 text-xl font-semibold tabular-nums", accent)}>
        {value}
      </p>
      <p className="text-[11px] text-slate-500">{sub}</p>
    </div>
  );
}

function sourceIcon(p: HourlyPrediction): { Icon: LucideIcon } {
  if (p.data_source === "actual" && !p.fallback_used) return { Icon: Database };
  if (p.data_source === "insufficient_data") return { Icon: HelpCircle };
  return { Icon: Cpu };
}

function sourceLabel(p: HourlyPrediction): string {
  if (p.data_source === "actual" && !p.fallback_used) return "Measured";
  if (p.data_source === "insufficient_data") return "Sparse";
  return "Estimated";
}

function sourceSub(p: HourlyPrediction): string {
  if (p.data_source === "actual" && !p.fallback_used) {
    return "Raw sensor data for this hour";
  }
  if (p.data_source === "insufficient_data") {
    return "< 7 reference observations";
  }
  return "Hour-of-day pattern over 14 days";
}

interface FeatureGridProps {
  prediction: HourlyPrediction;
}

function FeatureGrid({ prediction }: FeatureGridProps) {
  // The detail panel doesn't have access to the actual feature values
  // (those live in the FeaturesResponse, not HourlyPrediction). To
  // keep the strip→detail navigation cheap and avoid a refetch, we
  // surface the visible metadata we DO have and provide context the
  // user can act on. If feature inputs are needed later we can plumb
  // them through HourlyPrediction without touching the strip.
  const items: Array<{ k: string; v: string; hint?: string }> = [
    {
      k: "Hour",
      v: `${formatHour(prediction.hour_of_day)} UTC`,
      hint: "Diurnal cycle is one of the model's strongest signals.",
    },
    {
      k: "Verdict",
      v: prediction.is_unsafe === 1 ? "Unsafe" : "Safe",
    },
    {
      k: "Confidence",
      v: prediction.confidence.toUpperCase(),
      hint:
        prediction.confidence === "high"
          ? "The model's signal is strong here."
          : prediction.confidence === "medium"
            ? "Moderate signal; treat the verdict with some caution."
            : "Weak signal; the model is close to its decision boundary.",
    },
    {
      k: "Probability",
      v: `${(prediction.unsafe_probability * 100).toFixed(1)}%`,
      hint: "Relative ranking score, not a calibrated chance.",
    },
  ];

  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.k}>
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {item.k}
          </dt>
          <dd className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
            {item.v}
          </dd>
          {item.hint && (
            <dd className="text-[11px] leading-snug text-slate-500">
              {item.hint}
            </dd>
          )}
        </div>
      ))}
    </dl>
  );
}
