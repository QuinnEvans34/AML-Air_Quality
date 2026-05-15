/**
 * GET /api/health — server-side proxy to the FastAPI /health endpoint.
 *
 * The browser never talks to FastAPI directly per the Decision 8
 * architecture commitment. The handler returns the upstream
 * three-field W6 response shape (status, model_name, stage) on
 * success, or a 503 with a synthetic shape on any failure so the
 * HealthBadge component can render an "offline" state without
 * needing to introspect different error shapes.
 */

import { NextResponse } from "next/server";

import { FASTAPI_URL } from "@/lib/constants";
import type { HealthResponse } from "@/lib/types";

/** Disable Next.js route-level caching so the badge always reflects truth. */
export const dynamic = "force-dynamic";

const OFFLINE: HealthResponse = {
  status: "fastapi_unreachable",
  model_name: "",
  stage: "",
};

export async function GET(): Promise<NextResponse> {
  try {
    const upstream = await fetch(`${FASTAPI_URL}/health`, {
      method: "GET",
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json(OFFLINE, { status: 503 });
    }
    const body = (await upstream.json()) as HealthResponse;
    return NextResponse.json(body);
  } catch {
    return NextResponse.json(OFFLINE, { status: 503 });
  }
}
