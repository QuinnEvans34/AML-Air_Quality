/**
 * POST /api/predict — server-side proxy to the FastAPI /predict endpoint.
 *
 * Validates the incoming JSON body against the Contract 3 shape
 * before forwarding so FastAPI never sees malformed input from the
 * browser. Returns the Contract 4 response on success or a pass-through
 * error body on FastAPI failure.
 */

import { NextRequest, NextResponse } from "next/server";

import { FASTAPI_URL, FEATURE_COLS, LOCATION_KEYS } from "@/lib/constants";
import type { PredictResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Runtime validation of an incoming body against PredictRequest. We
 * intentionally don't pull in zod or a schema lib — the shape is
 * small and the dependency-minimum policy in the Entry 9 prompt
 * says no new deps without written reason.
 */
function isValidPredictRequest(
  x: unknown,
): x is { location: string } & Record<(typeof FEATURE_COLS)[number], number> {
  if (!x || typeof x !== "object") return false;
  const obj = x as Record<string, unknown>;
  if (typeof obj.location !== "string") return false;
  if (!LOCATION_KEYS.includes(obj.location as (typeof LOCATION_KEYS)[number])) {
    return false;
  }
  for (const col of FEATURE_COLS) {
    if (typeof obj[col] !== "number" || !Number.isFinite(obj[col] as number)) {
      return false;
    }
  }
  return true;
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { detail: "Request body must be valid JSON" },
      { status: 400 },
    );
  }

  if (!isValidPredictRequest(body)) {
    return NextResponse.json(
      {
        detail:
          "Request body does not match Contract 3 (location + 9 feature columns)",
      },
      { status: 422 },
    );
  }

  try {
    const upstream = await fetch(`${FASTAPI_URL}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!upstream.ok) {
      let detail = `FastAPI returned ${upstream.status}`;
      try {
        const errBody = (await upstream.json()) as { detail?: string };
        if (typeof errBody.detail === "string") detail = errBody.detail;
      } catch {
        /* fall through to default detail */
      }
      return NextResponse.json({ detail }, { status: upstream.status });
    }
    const data = (await upstream.json()) as PredictResponse;
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        detail: `FastAPI unreachable: ${err instanceof Error ? err.message : String(err)}`,
      },
      { status: 503 },
    );
  }
}
