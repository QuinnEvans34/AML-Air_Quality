/**
 * GET /api/trend — recent raw pm25 series for the trend chart.
 *
 * Query params:
 *   - location  (required) one of LocationKey
 *   - days      (optional, default 7, max 30)
 */

import { NextRequest, NextResponse } from "next/server";

import { LOCATION_KEYS, type LocationKey } from "@/lib/constants";
import { buildTrendSeries } from "@/lib/featurePrep";
import type { TrendPoint } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const params = req.nextUrl.searchParams;
  const location = params.get("location");
  const daysRaw = params.get("days") ?? "7";

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

  const days = Math.min(
    30,
    Math.max(1, Number.parseInt(daysRaw, 10) || 7),
  );

  try {
    const anchorIsoDate = new Date().toISOString().slice(0, 10);
    const points: TrendPoint[] = await buildTrendSeries(
      location as LocationKey,
      anchorIsoDate,
      days,
    );
    return NextResponse.json({
      location: location as LocationKey,
      days,
      points,
    });
  } catch (err) {
    return NextResponse.json(
      {
        detail:
          err instanceof Error ? err.message : "Unknown error building trend",
      },
      { status: 500 },
    );
  }
}
