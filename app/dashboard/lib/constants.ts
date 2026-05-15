/**
 * Mirror of include/src/constants.py — keep these in sync.
 *
 * SOURCE OF TRUTH: include/src/constants.py
 *
 * If you change a value here, change it in the Python file too AND
 * update INTERFACE.md "Shared Constants". The dashboard mirrors only
 * the subset of constants it actually uses. See INTERFACE.md
 * "Shared Constants" for the canonical list.
 */

/** EPA unsafe-for-sensitive-groups boundary in μg/m³. */
export const UNSAFE_THRESHOLD = 35.4 as const;

export type LocationKey = "red_butte" | "smithfield" | "ledges";

export const TARGET_LOCATIONS: Record<
  LocationKey,
  { id: number; label: string; region: string }
> = {
  red_butte: {
    id: 3318370,
    label: "Red Butte",
    region: "Salt Lake County",
  },
  smithfield: {
    id: 305,
    label: "Smithfield",
    region: "Cache Valley",
  },
  ledges: {
    id: 6158842,
    label: "Ledges",
    region: "Snow Canyon · St. George",
  },
};

export const LOCATION_KEYS = Object.keys(TARGET_LOCATIONS) as LocationKey[];

/**
 * Number of prior days of raw PM2.5 the dashboard reads to build the
 * "recent hourly pattern" lookup used for future-date feature prep.
 * Decision 8 in INTERFACE.md.
 */
export const REFERENCE_WINDOW_DAYS = 14;

/**
 * Minimum observations per hour-of-day before we trust the pattern
 * for the recent-pattern fallback. Below this threshold the dashboard
 * still returns features for the row but flags it as inconclusive so
 * the UI can mark it low-confidence.
 */
export const MIN_PATTERN_OBSERVATIONS = 7;

/**
 * Contract 3 feature column names in the exact order serve.py's model
 * expects. Must stay identical to include/src/constants.py
 * (Contract 3) and serve.py's FEATURE_COLS.
 */
export const FEATURE_COLS = [
  "pm25_lag_1h",
  "pm25_lag_3h",
  "pm25_lag_24h",
  "pm25_rolling_mean_3h",
  "pm25_rolling_std_3h",
  "hour_of_day",
  "day_of_week",
  "month_of_year",
  "is_weekend",
] as const;

export type FeatureCol = (typeof FEATURE_COLS)[number];

/**
 * Decision 7 user-facing confidence buckets (≥0.70 high, ≥0.40 medium,
 * <0.40 low). These bucket the raw `unsafe_probability` so the UI does
 * not display a calibration-unsafe raw percentage to non-technical
 * users.
 */
export const CONFIDENCE_HIGH_MIN = 0.7;
export const CONFIDENCE_MEDIUM_MIN = 0.4;

/**
 * FastAPI base URL. Read from env var or default to localhost.
 * Server-side only — never expose this to the browser; the browser
 * talks to Next.js API routes which proxy to FastAPI internally.
 */
export const FASTAPI_URL =
  process.env.FASTAPI_URL ?? "http://localhost:8000";

/**
 * Raw data directory the dashboard reads for the recent-pattern
 * lookup. Defaults to the canonical path inside the AirAlert repo.
 * Server-side only.
 */
export const RAW_DATA_DIR =
  process.env.RAW_DATA_DIR ?? "../../include/data/raw";
