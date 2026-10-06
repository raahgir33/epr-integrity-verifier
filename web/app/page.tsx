import { getHealth } from "@/lib/api";

export default async function Home() {
  let health;
  let error: string | null = null;

  try {
    health = await getHealth();
  } catch {
    error = "API unreachable";
  }

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <h1 className="text-2xl font-semibold text-slate-900">EPR Integrity Verifier</h1>

      {error ? (
        <p className="mt-4 text-red-700">{error}</p>
      ) : (
        <dl className="mt-4 space-y-1 text-slate-700">
          <div>
            <dt className="inline font-medium">Status:</dt> <dd className="inline">{health!.status}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Model:</dt> <dd className="inline">{health!.model}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Region:</dt> <dd className="inline">{health!.region}</dd>
          </div>
        </dl>
      )}
    </main>
  );
}
