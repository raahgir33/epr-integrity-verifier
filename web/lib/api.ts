export type Health = {
  status: string;
  model: string;
  region: string;
};

export async function getHealth(): Promise<Health> {
  const baseUrl = process.env.API_BASE_URL ?? "http://localhost:8080";
  const response = await fetch(`${baseUrl}/health`, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`API /health returned ${response.status}`);
  }

  return response.json();
}
