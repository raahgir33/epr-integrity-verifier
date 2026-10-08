// Proxies GET /documents/{docId}/file so documents open same-origin and
// API_BASE_URL stays server-side (never baked into client JS via
// NEXT_PUBLIC_*, per CLAUDE.md §6's Next.js conventions).

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ docId: string }> },
): Promise<Response> {
  const { docId } = await params;
  const baseUrl = process.env.API_BASE_URL ?? "http://localhost:8080";
  const response = await fetch(`${baseUrl}/documents/${encodeURIComponent(docId)}/file`, {
    cache: "no-store",
  });

  if (!response.ok || !response.body) {
    return new Response(null, { status: response.status });
  }

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const cacheControl = response.headers.get("cache-control");
  if (cacheControl) headers.set("cache-control", cacheControl);

  return new Response(response.body, { status: response.status, headers });
}
