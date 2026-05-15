/**
 * Typed client wrappers for the dashboard's same-origin API routes.
 *
 * The browser side never talks to FastAPI directly — it always goes
 * through Next.js API routes under /api/*. These functions wrap the
 * fetch calls with the right HTTP method, JSON serialization, and
 * typed response shapes.
 *
 * This file is safe to import from both client and server components.
 * Server-side fetch falls back to the same /api/ URL — Next.js will
 * route it internally without making a real network round trip.
 */

import type {
  FeaturesResponse,
  HealthResponse,
  HourlyPrediction,
  PredictRequest,
  PredictResponse,
  TrendPoint,
} from "./types";
import type { LocationKey } from "./constants";
import { confidenceBucket } from "./plainLanguage";

/**
 * Error thrown by any of the wrappers when the API returns non-2xx
 * or the response cannot be parsed. Components catch this to render
 * graceful error states (e.g. HealthBadge red dot).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | undefined;

  constructor(status: number, detail?: string) {
    super(
      `API request failed with status ${status}${detail ? `: ${detail}` : ""}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Resolve the API base — empty on the client (relative), full on server. */
function apiBase(): string {
  // On the browser, "" means "same origin." On the server in dev, we
  // need an absolute URL so that fetch can resolve it; Next.js sets
  // VERCEL_URL / NEXT_PUBLIC_VERCEL_URL in production, but for local
  // we fall through to localhost:3000.
  if (typeof window !== "undefined") return "";
  return process.env.NEXT_PUBLIC_DASHBOARD_URL ?? "http://localhost:3000";
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** GET /api/health — proxies FastAPI health endpoint. */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${apiBase()}/api/health`, {
    method: "GET",
    cache: "no-store",
  });
  return jsonOrThrow<HealthResponse>(res);
}

/**
 * POST /api/predict — proxies FastAPI predict endpoint.
 *
 * @param payload Contract 3 request body. The `location` field selects
 *                which per-location model FastAPI will use.
 */
export async function postPredict(
  payload: PredictRequest,
): Promise<PredictResponse> {
  const res = await fetch(`${apiBase()}/api/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return jsonOrThrow<PredictResponse>(res);
}

/**
 * GET /api/features — server-side feature prep.
 *
 * @param location Location key.
 * @param fromIso  ISO 8601 UTC datetime for the first hour to predict.
 * @param hours    Number of consecutive hourly rows.
 */
export async function getFeatures(
  location: LocationKey,
  fromIso: string,
  hours: number,
): Promise<FeaturesResponse> {
  const params = new URLSearchParams({
    location,
    from: fromIso,
    hours: String(hours),
  });
  const res = await fetch(`${apiBase()}/api/features?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });
  return jsonOrThrow<FeaturesResponse>(res);
}

/**
 * GET /api/trend — last-N-days of raw pm25 for the trend chart.
 *
 * @param location Location key.
 * @param days     How many days of history. Default 7.
 */
export async function getTrend(
  location: LocationKey,
  days = 7,
): Promise<{ location: LocationKey; days: number; points: TrendPoint[] }> {
  const params = new URLSearchParams({
    location,
    days: String(days),
  });
  const res = await fetch(`${apiBase()}/api/trend?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });
  return jsonOrThrow<{
    location: LocationKey;
    days: number;
    points: TrendPoint[];
  }>(res);
}

/**
 * Convenience: run the full predict-many-rows-then-render pipeline.
 * Calls /api/features once for the requested range, then POSTs each
 * row to /api/predict, then folds the per-hour predictions into the
 * UI-ready HourlyPrediction shape (with confidence bucket attached).
 *
 * If `serial` is true (default), predictions are issued one at a time
 * to avoid hammering FastAPI. For an 11-hour range this is roughly
 * 11 sequential requests, each completing in ~100 ms locally — well
 * within the dashboard's responsiveness budget. Set `serial=false`
 * to fire them in parallel if the server can take it.
 */
export async function predictRange(
  location: LocationKey,
  fromIso: string,
  hours: number,
  options: { serial?: boolean } = {},
): Promise<{
  rows: HourlyPrediction[];
  any_fallback_used: boolean;
  reference_window_days: number;
}> {
  const features = await getFeatures(location, fromIso, hours);

  const issue = async (
    row: (typeof features.rows)[number],
  ): Promise<HourlyPrediction> => {
    const result = await postPredict({
      location,
      ...row.features,
    });
    return {
      timestamp: row.timestamp,
      hour_of_day: row.features.hour_of_day,
      is_unsafe: result.is_unsafe,
      unsafe_probability: result.unsafe_probability,
      confidence: confidenceBucket(result.is_unsafe, result.unsafe_probability),
      data_source: row.data_source,
      fallback_used: row.fallback_used,
    };
  };

  let rows: HourlyPrediction[];
  if (options.serial === false) {
    rows = await Promise.all(features.rows.map(issue));
  } else {
    rows = [];
    for (const row of features.rows) {
      // eslint-disable-next-line no-await-in-loop
      rows.push(await issue(row));
    }
  }

  return {
    rows,
    any_fallback_used: features.any_fallback_used,
    reference_window_days: features.reference_window_days,
  };
}
