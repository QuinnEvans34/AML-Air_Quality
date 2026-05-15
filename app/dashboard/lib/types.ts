/**
 * TypeScript shapes for AirAlert Contracts 3 and 4 plus the dashboard's
 * internal types. Keep aligned with INTERFACE.md.
 */

import type { LocationKey, FeatureCol } from "./constants";

/** Values for the nine Contract 3 feature columns. */
export type FeatureValues = Record<FeatureCol, number>;

/** Contract 3 — request body POSTed to /predict. */
export interface PredictRequest extends FeatureValues {
  location: LocationKey;
}

/** Contract 4 — response from /predict. */
export interface PredictResponse {
  is_unsafe: 0 | 1;
  unsafe_probability: number;
  threshold_used: number;
}

/** Contract 4 — response from /health (W6 shape, three fields). */
export interface HealthResponse {
  status: string;
  model_name: string;
  stage: string;
}

/**
 * Source flag for the feature values in one row. See Decision 8 in
 * INTERFACE.md and the "Feature-prep algorithm" section of the
 * dashboard plan.
 */
export type FeatureDataSource =
  | "actual"
  | "recent_pattern"
  | "insufficient_data";

/** One hour's worth of features built by /api/features. */
export interface FeatureRow {
  /** ISO 8601 UTC timestamp for this hour. */
  timestamp: string;
  /** The nine Contract 3 feature values for this hour. */
  features: FeatureValues;
  /** Where each lag/rolling value came from. */
  data_source: FeatureDataSource;
  /** True if any guard fired (sparse pattern, missing actuals). */
  fallback_used: boolean;
}

/** /api/features response payload. */
export interface FeaturesResponse {
  location: LocationKey;
  rows: FeatureRow[];
  reference_window_days: number;
  any_fallback_used: boolean;
}

/** One row's joined input + prediction, ready to render in the UI. */
export interface HourlyPrediction {
  timestamp: string;
  hour_of_day: number;
  is_unsafe: 0 | 1;
  unsafe_probability: number;
  confidence: "high" | "medium" | "low";
  data_source: FeatureDataSource;
  fallback_used: boolean;
}

/** Plain-language headline output from lib/plainLanguage.ts. */
export interface PlainLanguageVerdict {
  headline: string;
  recommendation: string;
  /** Overall confidence taken from the highest-stakes hour in the range. */
  confidence: "high" | "medium" | "low";
  /** True if any hour in the range was predicted unsafe. */
  any_unsafe: boolean;
}

/** Trend chart point — last-N-days raw pm25 for a location. */
export interface TrendPoint {
  timestamp: string;
  pm25: number;
  is_unsafe: boolean;
}
