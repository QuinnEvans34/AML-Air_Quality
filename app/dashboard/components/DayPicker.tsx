/**
 * DayPicker — horizontal row of weekday pills.
 *
 * Replaces the native <input type="date"> with a stakeholder-friendly
 * "Today / Tomorrow / next Friday" mental model. Defaults to today's
 * Mountain-Time date; renders 7 days forward.
 */

"use client";

import { clsx } from "clsx";
import { CalendarDays } from "lucide-react";

import { nextNDaysMT } from "@/lib/timezone";

interface DayPickerProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  daysAhead?: number;
}

export function DayPicker({
  value,
  onChange,
  disabled,
  daysAhead = 7,
}: DayPickerProps) {
  const days = nextNDaysMT(daysAhead);
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <CalendarDays className="h-3.5 w-3.5" aria-hidden />
        <span id="day-label">Day</span>
      </div>
      <div
        role="radiogroup"
        aria-labelledby="day-label"
        className="grid grid-cols-7 gap-1.5"
      >
        {days.map((d) => {
          const isSelected = d.iso === value;
          return (
            <button
              key={d.iso}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onChange(d.iso)}
              className={clsx(
                "flex flex-col items-center rounded-xl border px-1 py-2 transition",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
                isSelected
                  ? "border-brand-600 bg-brand-600 text-white shadow-soft"
                  : "border-slate-200 bg-white text-slate-900 hover:border-slate-300",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <span
                className={clsx(
                  "text-[10px] font-semibold uppercase tracking-wider",
                  isSelected ? "text-brand-100" : "text-slate-500",
                )}
              >
                {d.weekday}
              </span>
              <span className="text-sm font-semibold tabular-nums">
                {d.monthDay}
              </span>
              {d.isToday && (
                <span
                  className={clsx(
                    "mt-0.5 text-[9px] font-medium",
                    isSelected ? "text-brand-100" : "text-brand-600",
                  )}
                >
                  TODAY
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
