// Proxies GET /alerts so the client-side run panel can look up the alert a
// finished run produced (lib/api.ts's API_BASE_URL is server-only, per
// internal engineering notes §6).

import { ApiError, getAlerts } from "@/lib/api";
import { NextResponse } from "next/server";

export async function GET(): Promise<Response> {
  try {
    return NextResponse.json(await getAlerts());
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.detail ?? error.message }, { status: error.status });
    }
    throw error;
  }
}
