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

/** A K-5 elementary served by the location's air shed. */
export interface School {
  name: string;
  address: string;
}

/** Stakeholder-facing metadata for each target location. The label /
 *  region fields are kept for back-compat with components that haven't
 *  been refactored to surface school names. */
export interface LocationMeta {
  id: number;
  label: string;
  region: string;
  primary_school: string;
  district: string;
  sensor_label: string;
  nearby_schools: School[];
}

export const TARGET_LOCATIONS: Record<LocationKey, LocationMeta> = {
  red_butte: {
    id: 3318370,
    label: "Red Butte",
    region: "Salt Lake County",
    primary_school: "Bonneville Elementary",
    district: "Salt Lake City School District",
    sensor_label: "Red Butte sensor",
    nearby_schools: [
      { name: "Bonneville Elementary",   address: "1145 S 1900 E, Salt Lake City, UT 84108" },
      { name: "Indian Hills Elementary", address: "1340 E St Marys Way, Salt Lake City, UT 84108" },
      { name: "Wasatch Elementary",      address: "30 R St, Salt Lake City, UT 84103" },
      { name: "Uintah Elementary",       address: "1571 E 1300 S, Salt Lake City, UT 84105" },
    ],
  },
  smithfield: {
    id: 305,
    label: "Smithfield",
    region: "Cache Valley",
    primary_school: "Summit Elementary",
    district: "Cache County School District",
    sensor_label: "Smithfield sensor",
    nearby_schools: [
      { name: "Summit Elementary",      address: "100 N 200 W, Smithfield, UT 84335" },
      { name: "Birch Creek Elementary", address: "825 S Main St, Smithfield, UT 84335" },
      { name: "Heritage Elementary",    address: "75 N Main St, Smithfield, UT 84335" },
    ],
  },
  ledges: {
    id: 6158842,
    label: "Ledges",
    region: "Snow Canyon · St. George",
    primary_school: "Red Mountain Elementary",
    district: "Washington County School District",
    sensor_label: "Ledges sensor",
    nearby_schools: [
      { name: "Red Mountain Elementary",   address: "940 N 200 W, Ivins, UT 84738" },
      { name: "Diamond Valley Elementary", address: "5530 N Diamond Valley Dr, St. George, UT 84770" },
      { name: "Coral Cliffs Elementary",   address: "1955 W 530 N, St. George, UT 84770" },
    ],
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
