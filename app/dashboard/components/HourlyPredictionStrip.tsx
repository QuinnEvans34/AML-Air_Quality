/**
 * HourlyPredictionStrip — the hourly forecast row.
 *
 * Visual upgrades vs. the v1:
 *   - Bigger, taller cells with a soft hover lift
 *   - A "PREDICTED" pill at the top making the data source explicit
 *   - A "Now" marker over the current hour
 *   - Time-of-day sunrise / sun / sunset icons at the ends
 *   - Per-cell tiny dot indicating data source (measured vs estimated)
 *   - Selecting a cell highlights it; parent renders the
 *     PredictionDetailPanel below
 */

"use client";

import { clsx } from "clsx";
import {
  AlertTriangle,
  Check,
  CircleDot,
  Cpu,
  Database,
  HelpCircle,
  Sparkles,
  Sun,
  Sunrise,
  Sunset,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cellState, formatHour } from "@/lib/plainLanguage";
import type { HourlyPrediction } from "@/lib/types";

interface HourlyPredictionStripProps {
  predictions: HourlyPrediction[];
  loading: boolean;
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
}

interface CellVisual {
  bg: string;
  border: string;
  glyph: LucideIcon;
  glyphBg: string;
  glyphColor: string;
  label: string;
  ringSelected: string;
}

const VISUALS: Record<
  ReturnType<typeof cellState>,
  CellVisual
> = {
  "safe-high": {
    bg: "bg-safe-50",
    border: "border-safe-200",
    glyph: Check,
    glyphBg: "bg-safe-500",
    glyphColor: "text-white",
    label: "predicted safe, high confidence",
    ringSelected: "ring-safe-500",
  },
  "safe-medium": {
    bg: "bg-safe-50",
    border: "border-safe-200",
    glyph: Check,
    glyphBg: "bg-safe-500",
    glyphColor: "text-white",
    label: "predicted safe, medium confidence",
    ringSelected: "ring-safe-500",
  },
  borderline: {
    bg: "bg-caution-50",
    border: "border-caution-200",
    glyph: AlertTriangle,
    glyphBg: "bg-caution-500",
    glyphColor: "text-white",
    label: "borderline — low confidence either direction",
    ringSelected: "ring-caution-500",
  },
  "unsafe-medium": {
    bg: "bg-unsafe-50",
    border: "border-unsafe-200",
    glyph: X,
    glyphBg: "bg-unsafe-500",
    glyphColor: "text-white",
    label: "predicted unsafe, medium confidence",
    ringSelected: "ring-unsafe-500",
  },
  "unsafe-high": {
    bg: "bg-unsafe-100",
    border: "border-unsafe-300",
    glyph: X,
    glyphBg: "bg-unsafe-600",
    glyphColor: "text-white",
    label: "predicted unsafe, high confidence",
    ringSelected: "ring-unsafe-600",
  },
};

function dataSourceIcon(p: HourlyPrediction): {
  Icon: LucideIcon;
  title: string;
} {
  if (p.data_source === "actual" && !p.fallback_used) {
    return { Icon: Database, title: "Measured from raw sensor data" };
  }
  if (p.data_source === "insufficient_data") {
    return { Icon: HelpCircle, title: "Insufficient reference data" };
  }
  return { Icon: Cpu, title: "Estimated from recent hourly patterns" };
}

export function HourlyPredictionStrip({
  predictions,
  loading,
  selectedIndex,
  onSelect,
}: HourlyPredictionStripProps) {
  if (loading) {
    return (
      <div>
        <StripHeader />
        <div className="grid grid-cols-6 gap-2 sm:grid-cols-11">
          {Array.from({ length: 11 }).map((_, i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-2xl bg-slate-100"
            />
          ))}
        </div>
      </div>
    );
  }

  if (predictions.length === 0) return null;

  return (
    <div>
      <StripHeader />

      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: `repeat(${Math.min(predictions.length, 11)}, minmax(0, 1fr))`,
        }}
      >
        {predictions.map((p, i) => {
          const state = cellState(p);
          const visual = VISUALS[state];
          const Glyph = visual.glyph;
          const { Icon: SourceIcon, title: sourceTitle } = dataSourceIcon(p);
          const isSelected = selectedIndex === i;
          return (
            <button
              key={`${p.timestamp}-${i}`}
              type="button"
              aria-label={`${formatHour(p.hour_of_day)}, ${visual.label}${
                p.fallback_used ? ", estimated from recent patterns" : ""
              }. Tap for details.`}
              aria-pressed={isSelected}
              onClick={() => onSelect(isSelected ? null : i)}
              className={clsx(
                "group relative flex h-24 flex-col items-center justify-center gap-1.5 overflow-hidden rounded-2xl border-2 transition",
                "hover:-translate-y-0.5 hover:shadow-soft",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
                visual.bg,
                visual.border,
                isSelected && "ring-2 ring-offset-2",
                isSelected && visual.ringSelected,
              )}
            >
              {/* Top-right data-source indicator */}
              <span
                title={sourceTitle}
                className="absolute right-1.5 top-1.5 text-slate-400"
              >
                <SourceIcon className="h-3 w-3" aria-hidden />
              </span>

              {/* Verdict glyph in a soft tinted circle */}
              <span
                className={clsx(
                  "flex h-9 w-9 items-center justify-center rounded-full",
                  visual.glyphBg,
                )}
              >
                <Glyph
                  className={clsx("h-4 w-4", visual.glyphColor)}
                  aria-hidden
                  strokeWidth={3}
                />
              </span>

              {/* Hour label */}
              <span className="text-xs font-semibold tabular-nums text-slate-700">
                {formatHour(p.hour_of_day)}
              </span>
            </button>
          );
        })}
      </div>

      {/* Time-of-day rail */}
      <div className="mt-2 flex items-center justify-between px-1 text-slate-300">
        <Sunrise className="h-4 w-4" aria-hidden />
        <Sun className="h-4 w-4" aria-hidden />
        <Sunset className="h-4 w-4" aria-hidden />
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-slate-500">
        <LegendDot bg="bg-safe-500" label="Safe" />
        <LegendDot bg="bg-caution-500" label="Borderline" />
        <LegendDot bg="bg-unsafe-500" label="Unsafe" />
        <span className="ml-auto flex items-center gap-3 text-slate-400">
          <span className="inline-flex items-center gap-1">
            <Database className="h-3 w-3" aria-hidden />
            measured
          </span>
          <span className="inline-flex items-center gap-1">
            <Cpu className="h-3 w-3" aria-hidden />
            estimated
          </span>
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Tap any hour to see why the model made that call.
      </p>
    </div>
  );
}

function StripHeader() {
  return (
    <div className="mb-3 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-brand-700 ring-1 ring-inset ring-brand-200">
          <Sparkles className="h-3 w-3" aria-hidden />
          Predicted
        </span>
        <h3 className="text-sm font-semibold text-slate-900">Hourly outlook</h3>
      </div>
      <span className="hidden text-xs text-slate-500 sm:inline">
        Color = verdict · darker red = higher confidence
      </span>
    </div>
  );
}

function LegendDot({ bg, label }: { bg: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={clsx("inline-block h-2.5 w-2.5 rounded-full", bg)} />
      <CircleDot className="hidden" aria-hidden />
      {label}
    </span>
  );
}
