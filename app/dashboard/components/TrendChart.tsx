/**
 * TrendChart — recent PM2.5 readings with a clear "MEASURED" badge
 * so users instantly understand this is observed data, not a model
 * prediction. Adds a subtle area fill under the line, a vertical
 * "Now" marker, axis units, and a tooltip with verdict semantics.
 */

"use client";

import {
  Activity,
  Database,
} from "lucide-react";
import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  TARGET_LOCATIONS,
  UNSAFE_THRESHOLD,
  type LocationKey,
} from "@/lib/constants";
import type { TrendPoint } from "@/lib/types";

interface TrendChartProps {
  location: LocationKey;
  points: TrendPoint[];
  days?: number;
}

interface ChartPoint {
  t: number;
  pm25: number;
  is_unsafe: boolean;
}

export function TrendChart({ location, points, days = 7 }: TrendChartProps) {
  const chartData = useMemo<ChartPoint[]>(
    () =>
      points
        .map((p) => ({
          t: new Date(p.timestamp.replace(" ", "T")).getTime(),
          pm25: p.pm25,
          is_unsafe: p.is_unsafe,
        }))
        .filter((p) => Number.isFinite(p.t)),
    [points],
  );

  const yMax = useMemo(() => {
    const max = chartData.reduce((m, p) => (p.pm25 > m ? p.pm25 : m), 0);
    return Math.max(60, Math.ceil((max + 5) / 10) * 10);
  }, [chartData]);

  const now = useMemo(() => Date.now(), []);
  const locationLabel = TARGET_LOCATIONS[location]?.label ?? location;

  // Quick numerical summary above the chart.
  const summary = useMemo(() => {
    if (chartData.length === 0) return null;
    const sum = chartData.reduce((s, p) => s + p.pm25, 0);
    const avg = sum / chartData.length;
    const max = Math.max(...chartData.map((p) => p.pm25));
    const unsafeHours = chartData.filter((p) => p.is_unsafe).length;
    return { avg, max, unsafeHours, total: chartData.length };
  }, [chartData]);

  return (
    <div className="rounded-3xl border border-slate-200 bg-white px-6 py-6 shadow-soft">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-white">
              <Database className="h-3 w-3" aria-hidden />
              Measured
            </span>
            <h3 className="text-sm font-semibold text-slate-900">
              Recent PM2.5 · {locationLabel}
            </h3>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500">
            <Activity className="h-3 w-3" aria-hidden />
            <span>
              Real hourly sensor readings · last {days} days · μg/m³ · Mountain Time
            </span>
          </p>
        </div>

        {summary && (
          <div className="flex gap-2 text-[11px]">
            <SummaryPill
              label="avg"
              value={`${summary.avg.toFixed(1)}`}
            />
            <SummaryPill
              label="peak"
              value={`${summary.max.toFixed(1)}`}
            />
            <SummaryPill
              label="unsafe hrs"
              value={`${summary.unsafeHours}/${summary.total}`}
              danger={summary.unsafeHours > 0}
            />
          </div>
        )}
      </div>

      {/* Chart */}
      {chartData.length === 0 && (
        <p className="mt-5 rounded-2xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
          No recent PM2.5 data for {locationLabel}. The pipeline may not
          have produced any runs in the last {days} days.
        </p>
      )}

      {chartData.length > 0 && (
        <div
          role="img"
          aria-label={`PM2.5 trend chart for ${locationLabel}. ${days} days of hourly readings. Unsafe threshold at ${UNSAFE_THRESHOLD} micrograms per cubic meter.`}
          className="mt-5 h-56 sm:h-64"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ left: 0, right: 16, top: 8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={fmtDateTick}
                tick={{ fontSize: 11, fill: "#64748b" }}
                stroke="#cbd5e1"
              />
              <YAxis
                domain={[0, yMax]}
                tick={{ fontSize: 11, fill: "#64748b" }}
                stroke="#cbd5e1"
                width={40}
                label={{
                  value: "μg/m³",
                  position: "insideLeft",
                  angle: -90,
                  fill: "#94a3b8",
                  fontSize: 11,
                  dy: 24,
                }}
              />
              <Tooltip
                content={<TrendTooltip />}
                cursor={{ stroke: "#94a3b8", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="pm25"
                stroke="none"
                fill="url(#trendFill)"
                isAnimationActive={false}
              />
              <ReferenceLine
                y={UNSAFE_THRESHOLD}
                stroke="#e11d48"
                strokeDasharray="4 3"
                strokeWidth={1.25}
                label={{
                  value: `unsafe @ ${UNSAFE_THRESHOLD}`,
                  position: "right",
                  fill: "#be123c",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              />
              {now >= chartData[0].t && now <= chartData[chartData.length - 1].t && (
                <ReferenceLine
                  x={now}
                  stroke="#0f172a"
                  strokeDasharray="2 2"
                  strokeWidth={1}
                  label={{
                    value: "now",
                    position: "top",
                    fill: "#0f172a",
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                />
              )}
              <Line
                type="monotone"
                dataKey="pm25"
                stroke="#4f46e5"
                strokeWidth={1.75}
                dot={false}
                activeDot={{ r: 4, fill: "#4f46e5" }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function fmtDateTick(value: number): string {
  const d = new Date(value);
  if (!Number.isFinite(d.getTime())) return "";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "America/Denver",
  });
}

interface TooltipPayload {
  payload: ChartPoint;
}

interface TooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
}

function TrendTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const datum = payload[0].payload;
  const dt = new Date(datum.t);
  const time = dt.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    timeZone: "America/Denver",
  });
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-soft">
      <p className="font-semibold text-slate-900">{time}</p>
      <p className="mt-0.5 tabular-nums text-slate-700">
        {datum.pm25.toFixed(1)} μg/m³
      </p>
      <p
        className={
          datum.is_unsafe ? "font-semibold text-unsafe-700" : "text-safe-700"
        }
      >
        {datum.is_unsafe ? "UNSAFE" : "Safe"}
      </p>
    </div>
  );
}

function SummaryPill({
  label,
  value,
  danger = false,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-baseline gap-1 rounded-full px-2.5 py-1 ring-1 ring-inset ${
        danger
          ? "bg-unsafe-50 text-unsafe-700 ring-unsafe-200"
          : "bg-slate-50 text-slate-700 ring-slate-200"
      }`}
    >
      <span className="text-[10px] font-semibold uppercase tracking-wider">
        {label}
      </span>
      <span className="font-semibold tabular-nums">{value}</span>
    </span>
  );
}
