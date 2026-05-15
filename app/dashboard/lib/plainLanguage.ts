/**
 * Plain-language headline generator for the dashboard.
 *
 * The W7A1 rubric is explicit: "A user who knows nothing about PM2.5
 * thresholds or machine learning should understand what the prediction
 * means and what they should do about it." A bare `is_unsafe: 1` is
 * not sufficient. This module turns an array of HourlyPrediction
 * objects into a narrative sentence + a concrete recommendation,
 * with one of three confidence buckets per Decision 7.
 *
 * Pure function — no IO, no React state. Imported by the page
 * composition in app/page.tsx (sub-phase 3e) and by any component
 * that surfaces a textual outlook.
 */

import {
  CONFIDENCE_HIGH_MIN,
  CONFIDENCE_MEDIUM_MIN,
  TARGET_LOCATIONS,
  type LocationKey,
} from "./constants";
import type { HourlyPrediction, PlainLanguageVerdict } from "./types";

/**
 * Map a raw `unsafe_probability` into the Decision 7 confidence bucket.
 * The buckets are intentional UX boundaries — see INTERFACE.md
 * Decision 7 reasoning.
 *
 * For an unsafe prediction (is_unsafe=1), a HIGHER probability means
 * we're MORE confident the air is unsafe.
 * For a safe prediction (is_unsafe=0), we map the COMPLEMENT — a
 * lower unsafe probability means we're more confident the air is safe.
 */
export function confidenceBucket(
  is_unsafe: 0 | 1,
  unsafe_probability: number,
): "high" | "medium" | "low" {
  const certainty = is_unsafe === 1
    ? unsafe_probability
    : 1 - unsafe_probability;
  if (certainty >= CONFIDENCE_HIGH_MIN) return "high";
  if (certainty >= CONFIDENCE_MEDIUM_MIN) return "medium";
  return "low";
}

/**
 * Format an hour (0..23) as a friendly "8 AM" / "1 PM" / "12 AM" /
 * "12 PM" string. The dashboard renders in the user's locale; this
 * function is for the dataset's UTC hours (matches the model's input
 * hour_of_day feature).
 */
export function formatHour(hour: number): string {
  const h = ((hour % 24) + 24) % 24;
  const period = h < 12 ? "AM" : "PM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display} ${period}`;
}

/** Format a Date as e.g. "Friday, May 15". */
export function formatDateLong(d: Date): string {
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

/**
 * Group adjacent unsafe hours into contiguous ranges so the headline
 * can say "between 2 PM and 4 PM" instead of listing every hour.
 *
 * Two hours are considered adjacent if they differ by exactly 1 in
 * `hour_of_day`. This works for the default 8 AM–6 PM range and
 * tolerates the case where the user picks a discontinuous selection
 * (the grouper returns multiple ranges).
 *
 * @returns Array of {start, end} ranges. `start` and `end` are
 *   inclusive hour-of-day integers. A single-hour event has
 *   `start === end`.
 */
export function groupConsecutiveUnsafe(
  predictions: HourlyPrediction[],
): Array<{ start: number; end: number }> {
  const unsafe = predictions
    .filter((p) => p.is_unsafe === 1)
    .slice()
    .sort((a, b) => a.hour_of_day - b.hour_of_day);
  if (unsafe.length === 0) return [];

  const ranges: Array<{ start: number; end: number }> = [];
  let runStart = unsafe[0].hour_of_day;
  let runEnd = unsafe[0].hour_of_day;
  for (let i = 1; i < unsafe.length; i++) {
    const hh = unsafe[i].hour_of_day;
    if (hh === runEnd + 1) {
      runEnd = hh;
    } else {
      ranges.push({ start: runStart, end: runEnd });
      runStart = hh;
      runEnd = hh;
    }
  }
  ranges.push({ start: runStart, end: runEnd });
  return ranges;
}

/**
 * Render one inclusive hour range as a human-readable string.
 *
 * Single-hour:    "at 2 PM"
 * Two adjacent:   "between 2 PM and 3 PM"  (end is inclusive)
 * Longer range:   "between 2 PM and 5 PM"
 */
function formatRange(range: { start: number; end: number }): string {
  if (range.start === range.end) {
    return `at ${formatHour(range.start)}`;
  }
  // For human readability we name the end-of-range as the END of the
  // unsafe HOUR — so a range with hours 14,15,16 reads "between 2 PM
  // and 5 PM" (the 4-PM hour ends at 5 PM).
  const endLabel = formatHour(range.end + 1);
  return `between ${formatHour(range.start)} and ${endLabel}`;
}

/**
 * Join multiple range strings with commas and "and" appropriately.
 *
 *  [r]            -> "between 2 PM and 4 PM"
 *  [r1, r2]       -> "between 9 AM and 11 AM, and between 2 PM and 4 PM"
 *  [r1, r2, r3]   -> "between …, between …, and between …"
 */
function joinRanges(ranges: Array<{ start: number; end: number }>): string {
  const parts = ranges.map(formatRange);
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]}, and ${parts[1]}`;
  return `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1)}`;
}

/**
 * Roll up the per-hour confidence buckets into one overall confidence
 * for the headline. We bias toward the most-actionable hour:
 *
 *   - If any unsafe hour exists, the overall confidence is the
 *     confidence of the unsafe hour with the highest unsafe_probability.
 *     This is the hour the user most needs to plan around.
 *   - If all hours are safe, the overall confidence is the LOWEST
 *     confidence across the range — so a single low-confidence safe
 *     hour pulls the overall down to "low," which is conservative.
 */
function overallConfidence(
  predictions: HourlyPrediction[],
): "high" | "medium" | "low" {
  if (predictions.length === 0) return "low";
  const unsafe = predictions.filter((p) => p.is_unsafe === 1);
  if (unsafe.length > 0) {
    const worst = unsafe.reduce((a, b) =>
      a.unsafe_probability >= b.unsafe_probability ? a : b,
    );
    return worst.confidence;
  }
  // All safe — find the row with the LEAST certainty (highest
  // unsafe_probability among the safe rows) and use its bucket.
  const least = predictions.reduce((a, b) =>
    a.unsafe_probability >= b.unsafe_probability ? a : b,
  );
  return least.confidence;
}

/**
 * Produce the headline + recommendation strings for the dashboard.
 *
 * @param locationKey  Selected location.
 * @param predictions  Array of per-hour predictions for the requested
 *                     range. Must be sorted ascending by hour_of_day
 *                     (the caller normally does this).
 * @returns            A PlainLanguageVerdict with headline,
 *                     recommendation, confidence, and any_unsafe.
 */
export function plainLanguageHeadline(
  locationKey: LocationKey,
  predictions: HourlyPrediction[],
): PlainLanguageVerdict {
  const meta = TARGET_LOCATIONS[locationKey];
  const locationLabel = meta ? meta.label : locationKey;
  const confidence = overallConfidence(predictions);
  const unsafeRanges = groupConsecutiveUnsafe(predictions);
  const any_unsafe = unsafeRanges.length > 0;

  if (!any_unsafe) {
    return {
      headline:
        `Air quality at ${locationLabel} is predicted to be SAFE ` +
        `across the requested hours.`,
      recommendation: "Outdoor activities should be fine.",
      confidence,
      any_unsafe: false,
    };
  }

  const rangeText = joinRanges(unsafeRanges);
  return {
    headline:
      `Air quality at ${locationLabel} is predicted to be UNSAFE ` +
      `${rangeText}.`,
    recommendation: "We recommend indoor recess during those hours.",
    confidence,
    any_unsafe: true,
  };
}

/**
 * Cell color/intensity selector for HourlyPredictionStrip.tsx.
 * Maps (is_unsafe, confidence) → one of five visual states:
 *
 *   safe-high  / safe-medium  → green
 *   safe-low                  → amber (borderline)
 *   unsafe-low                → amber (borderline)
 *   unsafe-medium             → red
 *   unsafe-high               → saturated red
 *
 * The strip component reads this and looks up its Tailwind classes.
 */
export type CellState =
  | "safe-high"
  | "safe-medium"
  | "borderline"
  | "unsafe-medium"
  | "unsafe-high";

export function cellState(p: HourlyPrediction): CellState {
  if (p.is_unsafe === 0) {
    return p.confidence === "low" ? "borderline" : `safe-${p.confidence}`;
  }
  if (p.confidence === "low") return "borderline";
  return `unsafe-${p.confidence}` as CellState;
}
