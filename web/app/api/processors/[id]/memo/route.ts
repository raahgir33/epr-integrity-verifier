// Proxies GET /processors/{id}/memo so the client-side EN/HI toggle (T13.5
// plan, Amendment C — the Hindi memo is only fetched once the viewer
// actually clicks HI, not eagerly on every page load) never calls the API
// directly (lib/api.ts's API_BASE_URL is server-only, per CLAUDE.md §6).

import { ApiError, getProcessorMemo } from "@/lib/api";
import { NextResponse } from "next/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  const lang = new URL(request.url).searchParams.get("lang") === "hi" ? "hi" : "en";
  try {
    const memo = await getProcessorMemo(id, lang);
    if (memo === null) {
      return NextResponse.json({ detail: "No memo available" }, { status: 404 });
    }
    return NextResponse.json(memo);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail ?? error.message }, { status: error.status });
    }
    throw error;
  }
}
