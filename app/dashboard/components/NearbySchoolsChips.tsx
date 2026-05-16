/**
 * NearbySchoolsChips — chip row naming the K-5 schools served by a
 * location's air shed. The primary school is brand-tinted; the rest
 * sit in slate. Hover any chip to see the school's street address.
 *
 * Compact mode drops the "Schools served" lead-in and shrinks the
 * type a notch — used inside the dense PredictionDetailPanel.
 */

"use client";

import { clsx } from "clsx";
import { School } from "lucide-react";

import { TARGET_LOCATIONS, type LocationKey } from "@/lib/constants";

interface NearbySchoolsChipsProps {
  location: LocationKey;
  /** Compact mode skips the lead-in label and shrinks padding;
   *  used inside dense cards like the detail panel. */
  compact?: boolean;
}

export function NearbySchoolsChips({
  location,
  compact = false,
}: NearbySchoolsChipsProps) {
  const meta = TARGET_LOCATIONS[location];
  const primary = meta.primary_school;
  return (
    <div
      className={clsx(
        "flex flex-wrap items-center gap-1.5",
        compact ? "text-[11px]" : "text-xs",
      )}
    >
      {!compact && (
        <span className="inline-flex items-center gap-1 font-semibold uppercase tracking-wider text-slate-500">
          <School className="h-3 w-3" aria-hidden />
          Schools served
        </span>
      )}
      {meta.nearby_schools.map((s) => {
        const isPrimary = s.name === primary;
        return (
          <span
            key={s.name}
            title={s.address}
            className={clsx(
              "inline-flex items-center rounded-full px-2.5 py-0.5 ring-1 ring-inset",
              isPrimary
                ? "bg-brand-50 text-brand-700 ring-brand-200 font-semibold"
                : "bg-slate-50 text-slate-700 ring-slate-200",
            )}
          >
            {s.name}
          </span>
        );
      })}
    </div>
  );
}
