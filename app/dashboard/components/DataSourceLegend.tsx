/**
 * DataSourceLegend — visual breakdown of where each hour's feature
 * values came from. Compact, icon-led, and color-coded so the user
 * can scan the dashboard's data-quality story at a glance.
 */

"use client";

import { Cpu, Database, HelpCircle } from "lucide-react";

import type { HourlyPrediction } from "@/lib/types";

interface DataSourceLegendProps {
  predictions: HourlyPrediction[];
  referenceWindowDays: number;
}

export function DataSourceLegend({
  predictions,
  referenceWindowDays,
}: DataSourceLegendProps) {
  if (predictions.length === 0) return null;

  const counts = predictions.reduce(
    (acc, p) => {
      if (p.data_source === "actual" && !p.fallback_used) acc.measured += 1;
      else if (p.data_source === "insufficient_data") acc.sparse += 1;
      else acc.estimated += 1;
      return acc;
    },
    { measured: 0, estimated: 0, sparse: 0 },
  );

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white/60 px-4 py-3 text-xs text-slate-600">
      <span className="font-semibold uppercase tracking-wider text-slate-500">
        Where the inputs came from
      </span>

      <SourcePill
        icon={Database}
        label="Measured"
        count={counts.measured}
        tone="slate"
      />
      <SourcePill
        icon={Cpu}
        label={`Estimated from ${referenceWindowDays}-day hourly patterns`}
        count={counts.estimated}
        tone="brand"
      />
      {counts.sparse > 0 && (
        <SourcePill
          icon={HelpCircle}
          label="Sparse — fewer than 7 reference observations"
          count={counts.sparse}
          tone="caution"
        />
      )}
    </div>
  );
}

interface SourcePillProps {
  icon: typeof Database;
  label: string;
  count: number;
  tone: "slate" | "brand" | "caution";
}

function SourcePill({ icon: Icon, label, count, tone }: SourcePillProps) {
  const palette = {
    slate: "bg-slate-50 text-slate-700 ring-slate-200",
    brand: "bg-brand-50 text-brand-700 ring-brand-200",
    caution: "bg-caution-50 text-caution-700 ring-caution-200",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ring-1 ring-inset ${palette}`}
    >
      <Icon className="h-3 w-3" aria-hidden />
      <span className="tabular-nums font-semibold">{count}</span>
      <span className="font-normal">{label}</span>
    </span>
  );
}
