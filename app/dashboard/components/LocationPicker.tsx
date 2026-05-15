/**
 * LocationPicker — segmented control with Lucide MapPin icon and
 * radiogroup semantics. Vertical stack on narrow screens for touch
 * targets; horizontal grid on wider.
 */

"use client";

import { clsx } from "clsx";
import { MapPin } from "lucide-react";

import {
  LOCATION_KEYS,
  TARGET_LOCATIONS,
  type LocationKey,
} from "@/lib/constants";

interface LocationPickerProps {
  value: LocationKey;
  onChange: (next: LocationKey) => void;
  disabled?: boolean;
}

export function LocationPicker({
  value,
  onChange,
  disabled,
}: LocationPickerProps) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <MapPin className="h-3.5 w-3.5" aria-hidden />
        <span id="location-label">Location</span>
      </div>
      <div
        role="radiogroup"
        aria-labelledby="location-label"
        className="grid grid-cols-3 gap-2"
      >
        {LOCATION_KEYS.map((key) => {
          const meta = TARGET_LOCATIONS[key];
          const isActive = key === value;
          return (
            <button
              key={key}
              role="radio"
              aria-checked={isActive}
              disabled={disabled}
              onClick={() => onChange(key)}
              className={clsx(
                "group relative rounded-xl border px-3 py-3 text-left transition",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
                isActive
                  ? "border-brand-600 bg-brand-600 text-white shadow-soft"
                  : "border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:bg-slate-50",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <span className="block text-sm font-medium leading-tight">
                {meta.label}
              </span>
              <span
                className={clsx(
                  "mt-0.5 block text-[11px] leading-tight",
                  isActive ? "text-brand-100" : "text-slate-500",
                )}
              >
                {meta.region}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
