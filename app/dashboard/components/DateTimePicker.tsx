/**
 * DateTimePicker — native date input dressed up with a Calendar icon.
 */

"use client";

import { Calendar } from "lucide-react";

interface DateTimePickerProps {
  value: string;
  onChange: (next: string) => void;
  minDate: string;
  maxDate: string;
  disabled?: boolean;
}

export function DateTimePicker({
  value,
  onChange,
  minDate,
  maxDate,
  disabled,
}: DateTimePickerProps) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <Calendar className="h-3.5 w-3.5" aria-hidden />
        <label htmlFor="dashboard-date">Date</label>
      </div>
      <input
        id="dashboard-date"
        type="date"
        value={value}
        min={minDate}
        max={maxDate}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-900 transition hover:border-slate-300 focus:border-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
      />
    </div>
  );
}
