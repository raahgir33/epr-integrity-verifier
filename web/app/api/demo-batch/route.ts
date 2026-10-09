// Proxies POST /demo/certificate-batch so the client component (lib/api.ts's
// API_BASE_URL is server-only, per CLAUDE.md §6) never calls the API
// directly. Forwards the API's own status code and detail message —
// T13's abuse gates (cooldown, daily cap, already running) return 429
// with a user-facing detail string the client shows verbatim.

import { ApiError, postDemoBatch } from "@/lib/api";
import { NextResponse } from "next/server";

export async function POST(request: Request): Promise<Response> {
  let batchId: string | undefined;
  try {
    const body: unknown = await request.json();
    if (body && typeof body === "object" && "batch_id" in body) {
      const value = (body as { batch_id: unknown }).batch_id;
      if (typeof value === "string") batchId = value;
    }
  } catch {
    // malformed JSON body — batchId stays undefined, handled below
  }
  if (!batchId) {
    return NextResponse.json({ detail: "batch_id is required" }, { status: 400 });
  }

  try {
    const result = await postDemoBatch(batchId);
    return NextResponse.json(result, { status: 202 });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail ?? error.message }, { status: error.status });
    }
    throw error;
  }
}
