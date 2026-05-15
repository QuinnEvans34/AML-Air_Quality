/**
 * Decision 8 feature-prep algorithm — server-side only.
 *
 * Builds the nine Contract 3 feature values for one (location, hour)
 * cell. Handles three time horizons cleanly:
 *
 *   1. Past hours with real raw data on disk → use actual measured
 *      pm25 values for lag/rolling features (data_source: "actual").
 *   2. Past hours with missing raw entries (sensor outage that day) →
 *      fall back to the recent-pattern mean for the matching
 *      hour-of-day (data_source: "recent_pattern", fallback_used: true).
 *   3. Future hours → always use the recent pattern (data_source:
 *      "recent_pattern"). If a target hour has fewer than
 *      MIN_PATTERN_OBSERVATIONS observations across the reference
 *      window, returns features anyway but marks fallback_used so the
 *      UI flags low-confidence.
 *
 * Temporal features (hour_of_day, day_of_week, month_of_year,
 * is_weekend) come from the requested datetime directly — no fallback
 * needed, no data source needed.
 *
 * See INTERFACE.md Decision 8 and the "Feature-prep algorithm"
 * section of docs/dashboard_implementation_plan.md for the canonical
 * spec.
 */

import {
  MIN_PATTERN_OBSERVATIONS,
  REFERENCE_WINDOW_DAYS,
  TARGET_LOCATIONS,
  type LocationKey,
} from "./constants";
import {
  readRawCsvForRange,
  isoDateDaysBefore,
  type RawPm25Row,
} from "./readRawCsv";
import type {
  FeatureDataSource,
  FeatureRow,
  FeatureValues,
} from "./types";

/** Hours in a 24h day. */
const HOURS_PER_DAY = 24;

/** Indexed lookup of pm25 values keyed by the ISO hour bucket. */
type PmIndex = Map<string, number>;

/** Pattern lookup: hour-of-day (0..23) → array of pm25 values seen at that hour. */
type HourPattern = Map<number, number[]>;

/** Convert an ISO timestamp string to "YYYY-MM-DDTHH" hour-bucket form. */
function hourBucket(isoTimestamp: string): string {
  // Allow either "2026-05-13 14:00:00+00:00" (pandas) or
  // "2026-05-13T14:00:00Z" (ISO 8601) — both come up in our pipeline.
  const normalized = isoTimestamp.replace(" ", "T");
  return normalized.slice(0, 13); // "YYYY-MM-DDTHH"
}

/** Convert a Date (assumed UTC) to "YYYY-MM-DDTHH" hour-bucket form. */
function dateToHourBucket(d: Date): string {
  return d.toISOString().slice(0, 13);
}

/**
 * Build the per-hour-bucket index AND the hour-of-day pattern from a
 * flat array of raw rows, filtered to one location_id.
 */
function buildIndexesForLocation(
  rows: RawPm25Row[],
  locationId: number,
): { hourly: PmIndex; pattern: HourPattern } {
  const hourly: PmIndex = new Map();
  const pattern: HourPattern = new Map();
  for (const row of rows) {
    if (row.location_id !== locationId) continue;
    if (!Number.isFinite(row.pm25)) continue;

    const bucket = hourBucket(row.timestamp);
    hourly.set(bucket, row.pm25);

    // hour-of-day extracted from the bucket suffix "...THH"
    const hh = Number.parseInt(bucket.slice(11, 13), 10);
    if (!Number.isFinite(hh)) continue;
    const list = pattern.get(hh) ?? [];
    list.push(row.pm25);
    pattern.set(hh, list);
  }
  return { hourly, pattern };
}

/** Mean of an array; returns 0 for empty input. */
function mean(values: number[]): number {
  if (values.length === 0) return 0;
  let sum = 0;
  for (const v of values) sum += v;
  return sum / values.length;
}

/** Population standard deviation (ddof=0); returns 0 for length < 2. */
function stdPop(values: number[]): number {
  if (values.length < 2) return 0;
  const m = mean(values);
  let sq = 0;
  for (const v of values) sq += (v - m) ** 2;
  return Math.sqrt(sq / values.length);
}

/**
 * Resolve the pm25 value to use for a given hour bucket, either from
 * actuals or from the recent-pattern fallback. Returns the value plus
 * a tag indicating which path was taken.
 */
function resolvePm25ForHour(
  bucket: string,
  hourOfDay: number,
  hourly: PmIndex,
  pattern: HourPattern,
): { value: number; fromPattern: boolean; insufficient: boolean } {
  const actual = hourly.get(bucket);
  if (actual !== undefined) {
    return { value: actual, fromPattern: false, insufficient: false };
  }
  const samples = pattern.get(hourOfDay) ?? [];
  if (samples.length === 0) {
    // No actuals AND no pattern observations for this hour — return
    // 0 with insufficient flag so the caller can mark the whole row
    // inconclusive.
    return { value: 0, fromPattern: true, insufficient: true };
  }
  return {
    value: mean(samples),
    fromPattern: true,
    insufficient: samples.length < MIN_PATTERN_OBSERVATIONS,
  };
}

/**
 * Build a single FeatureRow for one (location, targetDate, hour-of-day).
 *
 * @param locationKey  One of "red_butte" | "smithfield" | "ledges".
 * @param target       UTC Date for the hour we're predicting. Only the
 *                     date+hour portions are used — minutes/seconds
 *                     are ignored.
 * @param hourly       Hour-bucket → pm25 index for this location.
 * @param pattern      Hour-of-day → samples lookup for this location.
 */
function buildFeatureRow(
  locationKey: LocationKey,
  target: Date,
  hourly: PmIndex,
  pattern: HourPattern,
): FeatureRow {
  // Temporal features come straight from the requested datetime.
  // pandas.dayofweek puts Monday=0..Sunday=6; JS Date.getUTCDay puts
  // Sunday=0..Saturday=6. Map JS → pandas via (jsDay + 6) % 7 so the
  // dashboard's hour_of_day / day_of_week values match what transform.py
  // produced when the model was trained.
  const hour_of_day = target.getUTCHours();
  const day_of_week = (target.getUTCDay() + 6) % 7;
  const month_of_year = target.getUTCMonth() + 1;
  const is_weekend = day_of_week >= 5 ? 1 : 0;

  // We need pm25 at (target - 1h), (target - 3h), (target - 24h),
  // and the three hours (target - 1h, -2h, -3h) for rolling stats.
  // The rolling features in transform.py use the prior 3 hours
  // (t-3, t-2, t-1) — NOT including the current hour — so they match
  // the model's training distribution.
  const lagHours = [1, 3, 24];
  const rollingHours = [1, 2, 3]; // (t-1, t-2, t-3) shifted out of current

  const sources: FeatureDataSource[] = [];
  let fallback_used = false;
  let allInsufficient = true;

  const lagValues: Record<number, number> = {};
  for (const hoursAgo of lagHours) {
    const past = new Date(target);
    past.setUTCHours(past.getUTCHours() - hoursAgo);
    const bucket = dateToHourBucket(past);
    const hh = past.getUTCHours();
    const res = resolvePm25ForHour(bucket, hh, hourly, pattern);
    lagValues[hoursAgo] = res.value;
    sources.push(
      res.insufficient
        ? "insufficient_data"
        : res.fromPattern
          ? "recent_pattern"
          : "actual",
    );
    if (res.fromPattern || res.insufficient) fallback_used = true;
    if (!res.insufficient) allInsufficient = false;
  }

  const rollingValues: number[] = [];
  for (const hoursAgo of rollingHours) {
    const past = new Date(target);
    past.setUTCHours(past.getUTCHours() - hoursAgo);
    const bucket = dateToHourBucket(past);
    const hh = past.getUTCHours();
    const res = resolvePm25ForHour(bucket, hh, hourly, pattern);
    rollingValues.push(res.value);
    if (res.fromPattern || res.insufficient) fallback_used = true;
    if (!res.insufficient) allInsufficient = false;
  }

  const features: FeatureValues = {
    pm25_lag_1h: lagValues[1],
    pm25_lag_3h: lagValues[3],
    pm25_lag_24h: lagValues[24],
    pm25_rolling_mean_3h: mean(rollingValues),
    pm25_rolling_std_3h: stdPop(rollingValues),
    hour_of_day,
    day_of_week,
    month_of_year,
    is_weekend,
  };

  // Aggregate data_source — if every lookup was insufficient the row
  // is inconclusive; if any used the pattern the row is recent_pattern;
  // otherwise actual.
  let data_source: FeatureDataSource;
  if (allInsufficient) {
    data_source = "insufficient_data";
  } else if (sources.includes("recent_pattern") || fallback_used) {
    data_source = "recent_pattern";
  } else {
    data_source = "actual";
  }

  return {
    timestamp: target.toISOString(),
    features,
    data_source,
    fallback_used,
  };
}

/**
 * Public entry point: build the feature rows for `hours` consecutive
 * hourly cells starting at `fromIsoTimestamp` for the given location.
 *
 * @param locationKey       Location to predict for.
 * @param fromIsoTimestamp  ISO 8601 UTC datetime for the first hour.
 * @param hours             Number of consecutive hourly rows to return.
 *                          Clamped to [1, 24]; default 11 in the API
 *                          route caller.
 */
export async function buildFeatureRows(
  locationKey: LocationKey,
  fromIsoTimestamp: string,
  hours: number,
): Promise<FeatureRow[]> {
  const meta = TARGET_LOCATIONS[locationKey];
  if (!meta) {
    throw new Error(`Unknown location_key: ${locationKey}`);
  }
  const safeHours = Math.max(1, Math.min(24, Math.trunc(hours) || 1));

  const fromDate = new Date(fromIsoTimestamp);
  if (Number.isNaN(fromDate.getTime())) {
    throw new Error(`Invalid from datetime: ${fromIsoTimestamp}`);
  }

  // Reference window: the last REFERENCE_WINDOW_DAYS days strictly
  // before `fromDate`'s UTC date, PLUS the day of `fromDate` itself
  // and one extra day after, so that 24h-lag lookups for hours late
  // in the predicted range can still resolve to actuals when they
  // exist. This is a small expansion of the W7A1 plan's exact
  // wording but stays consistent with its intent.
  const anchorIsoDate = fromDate.toISOString().slice(0, 10);
  const fromWindow = isoDateDaysBefore(anchorIsoDate, REFERENCE_WINDOW_DAYS);
  const toWindow = isoDateDaysBefore(anchorIsoDate, -1); // day after the anchor

  const allRows = await readRawCsvForRange(fromWindow, toWindow);
  const { hourly, pattern } = buildIndexesForLocation(
    allRows,
    meta.id,
  );

  const out: FeatureRow[] = [];
  for (let i = 0; i < safeHours; i++) {
    const target = new Date(fromDate);
    target.setUTCHours(target.getUTCHours() + i);
    out.push(buildFeatureRow(locationKey, target, hourly, pattern));
  }
  return out;
}

/**
 * Helper for /api/trend — return the last `days` days of raw pm25
 * for a location as a flat array of {timestamp, pm25, is_unsafe}
 * trend points. Sorted ascending by timestamp.
 */
export async function buildTrendSeries(
  locationKey: LocationKey,
  anchorIsoDate: string,
  days = 7,
): Promise<Array<{ timestamp: string; pm25: number; is_unsafe: boolean }>> {
  const { UNSAFE_THRESHOLD } = await import("./constants");
  const meta = TARGET_LOCATIONS[locationKey];
  if (!meta) throw new Error(`Unknown location_key: ${locationKey}`);

  const fromWindow = isoDateDaysBefore(anchorIsoDate, days);
  const toWindow = anchorIsoDate;
  const rows = await readRawCsvForRange(fromWindow, toWindow);

  return rows
    .filter((r) => r.location_id === meta.id && Number.isFinite(r.pm25))
    .map((r) => ({
      timestamp: r.timestamp,
      pm25: r.pm25,
      is_unsafe: r.pm25 > UNSAFE_THRESHOLD,
    }));
}
