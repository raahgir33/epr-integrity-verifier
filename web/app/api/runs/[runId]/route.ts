// Proxies GET /runs/{runId} so the client-side polling component (lib/
// api.ts's API_BASE_URL is server-only, per internal engineering notes §6) never calls
// the API directly.

import { ApiError, getRun } from "@/lib/api";
import { NextResponse } from "next/server";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> },
): Promise<Response> {
  const { runId } = await params;
  try {
    const run = await getRun(runId);
    return NextResponse.json(run);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail ?? error.message }, { status: error.status });
    }
    throw error;
  }
}
