/**
 * HourRangeSlider — dual-thumb slider with Sunrise → Sun → Sunset
 * iconography that hints at "time of day."
 *
 * Style rules live in app/globals.css under .dual-thumb (brand-purple
 * thumb, soft glow shadow, hover scale).
 */

"use client";

import { Clock, Sunrise, Sun, Sunset } from "lucide-react";
import { useId } from "react";

import { formatHour } from "@/lib/plainLanguage";

interface HourRange {
  start: number;
  end: number;
}

interface HourRangeSliderProps {
  value: HourRange;
  onChange: (next: HourRange) => void;
  disabled?: boolean;
  min?: number;
  max?: number;
  maxSpan?: number;
}

export function HourRangeSlider({
  value,
  onChange,
  disabled,
  min = 0,
  max = 23,
  maxSpan = 12,
}: HourRangeSliderProps) {
  const startId = useId();
  const endId = useId();

  const { start, end } = value;
  const totalRange = max - min;
  const startPct = ((start - min) / totalRange) * 100;
  const endPct = ((end - min) / totalRange) * 100;

  const setStart = (raw: number) => {
    const clamped = Math.min(Math.max(raw, min), end);
    const span = end - clamped + 1;
    if (span > maxSpan) {
      onChange({ start: clamped, end: clamped + maxSpan - 1 });
    } else {
      onChange({ start: clamped, end });
    }
  };

  const setEnd = (raw: number) => {
    const clamped = Math.min(Math.max(raw, start), max);
    const span = clamped - start + 1;
    if (span > maxSpan) {
      onChange({ start: clamped - maxSpan + 1, end: clamped });
    } else {
      onChange({ start, end: clamped });
    }
  };

  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <Clock className="h-3.5 w-3.5" aria-hidden />
          <span>Hours</span>
        </div>
        <span className="text-xs tabular-nums text-slate-600">
          <span className="font-semibold text-slate-900">
            {formatHour(start)}
          </span>
          <span className="mx-1.5 text-slate-400">→</span>
          <span className="font-semibold text-slate-900">
            {formatHour(end)}
          </span>
        </span>
      </div>

      <div className="relative h-10 select-none">
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-slate-100" />
        <div
          className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-brand-500"
          style={{
            left: `${startPct}%`,
            width: `${Math.max(endPct - startPct, 0)}%`,
          }}
        />
        <input
          id={startId}
          aria-label="Start hour"
          type="range"
          min={min}
          max={max}
          step={1}
          value={start}
          disabled={disabled}
          onChange={(e) => setStart(Number.parseInt(e.target.value, 10))}
          className="dual-thumb absolute inset-0 h-full w-full appearance-none bg-transparent"
        />
        <input
          id={endId}
          aria-label="End hour"
          type="range"
          min={min}
          max={max}
          step={1}
          value={end}
          disabled={disabled}
          onChange={(e) => setEnd(Number.parseInt(e.target.value, 10))}
          className="dual-thumb absolute inset-0 h-full w-full appearance-none bg-transparent"
        />
      </div>

      <div className="mt-1 flex items-center justify-between text-slate-400">
        <Sunrise className="h-3.5 w-3.5" aria-hidden />
        <Sun className="h-3.5 w-3.5" aria-hidden />
        <Sunset className="h-3.5 w-3.5" aria-hidden />
      </div>
    </div>
  );
}
