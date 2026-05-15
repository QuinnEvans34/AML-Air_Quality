/**
 * GET /api/features — server-side feature prep.
 *
 * Reads pm25_*.csv files from the pipeline output via
 * lib/featurePrep and returns Contract 3 feature rows for the
 * requested (location, datetime, hours) range. This is the Node-only
 * route — it never talks to FastAPI; the dashboard then POSTs each
 * row to /api/predict in a follow-up step.
 *
 * Query params:
 *   - location  (required) one of LocationKey
 *   - from      (required) ISO 8601 UTC datetime for the first hour
 *   - hours     (optional, default 11, range 1..24)
 */

import { NextRequest, NextResponse } from "next/server";

import {
  LOCATION_KEYS,
  REFERENCE_WINDOW_DAYS,
  type LocationKey,
} from "@/lib/constants";
import { buildFeatureRows } from "@/lib/featurePrep";
import type { FeaturesResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const params = req.nextUrl.searchParams;
  const location = params.get("location");
  const from = params.get("from");
  const hoursRaw = params.get("hours") ?? "11";

  if (!location || !LOCATION_KEYS.includes(location as LocationKey)) {
    return NextResponse.json(
      {
        detail:
          "Query parameter 'location' must be one of: " +
          LOCATION_KEYS.join(", "),
      },
      { status: 400 },
    );
  }
  if (!from) {
    return NextResponse.json(
      { detail: "Query parameter 'from' is required (ISO 8601 UTC datetime)" },
      { status: 400 },
    );
  }

  const hours = Number.parseInt(hoursRaw, 10);
  if (!Number.isFinite(hours) || hours < 1 || hours > 24) {
    return NextResponse.json(
      { detail: "Query parameter 'hours' must be an integer 1..24" },
      { status: 400 },
    );
  }

  try {
    const rows = await buildFeatureRows(location as LocationKey, from, hours);
    const response: FeaturesResponse = {
      location: location as LocationKey,
      rows,
      reference_window_days: REFERENCE_WINDOW_DAYS,
      any_fallback_used: rows.some((r) => r.fallback_used),
    };
    return NextResponse.json(response);
  } catch (err) {
    return NextResponse.json(
      {
        detail:
          err instanceof Error
            ? err.message
            : "Unknown error building features",
      },
      { status: 500 },
    );
  }
}
