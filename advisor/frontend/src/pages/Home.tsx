import { useEffect, useState } from "react";
import RecommendationsPanel from "../components/RecommendationsPanel";

type HealthStatus = {
  status: string;
  database: string;
} | null;

function Home() {
  const [health, setHealth] = useState<HealthStatus>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data: HealthStatus) => {
        setHealth(data);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="mx-auto max-w-4xl px-6 py-16">
        <header className="mb-12">
          <h1 className="mb-2 text-4xl font-bold tracking-tight">
            Network Advisor
          </h1>
          <p className="text-lg text-gray-400">
            Camelot infrastructure management dashboard
          </p>
        </header>

        <div className="mb-8 text-gray-900">
          <RecommendationsPanel />
        </div>

        <section className="mb-8 rounded-lg border border-gray-700 bg-gray-800 p-6">
          <h2 className="mb-4 text-xl font-semibold">System Status</h2>
          <div className="flex items-center gap-3">
            <span
              className={`inline-block h-3 w-3 rounded-full ${
                error
                  ? "bg-red-500"
                  : health?.status === "ok"
                    ? "bg-green-500"
                    : "bg-yellow-500"
              }`}
            />
            <span className="text-gray-300">
              {error
                ? "Backend unreachable"
                : health
                  ? `Backend: ${health.status} | Database: ${health.database}`
                  : "Checking..."}
            </span>
          </div>
        </section>

        <section className="rounded-lg border border-gray-700 bg-gray-800 p-6">
          <h2 className="mb-4 text-xl font-semibold">Quick Links</h2>
          <ul className="space-y-2 text-gray-300">
            <li>
              <a
                href="/api/health"
                className="text-blue-400 underline hover:text-blue-300"
              >
                Health Endpoint
              </a>{" "}
              — Backend + database status
            </li>
          </ul>
        </section>

        <footer className="mt-16 text-sm text-gray-500">
          Camelot &mdash; Local-first home infrastructure
        </footer>
      </div>
    </div>
  );
}

export default Home;
