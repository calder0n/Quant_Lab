"use client";

import { useCallback, useEffect, useState } from "react";

type ComponentStatus = {
  status: "ok" | "error";
  detail: string | null;
};

type HealthResponse = {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  components: Record<string, ComponentStatus>;
};

const POLL_INTERVAL_MS = 5000;

const COMPONENT_LABELS: Record<string, string> = {
  api: "API (FastAPI)",
  database: "PostgreSQL",
  redis: "Redis",
};

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className="relative flex h-3 w-3">
      {ok && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
      )}
      <span
        className={`relative inline-flex h-3 w-3 rounded-full ${
          ok ? "bg-emerald-400" : "bg-rose-500"
        }`}
      />
    </span>
  );
}

function ComponentCard({
  name,
  component,
}: {
  name: string;
  component: ComponentStatus;
}) {
  const ok = component.status === "ok";
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">
          {COMPONENT_LABELS[name] ?? name}
        </h3>
        <StatusDot ok={ok} />
      </div>
      <p className={`mt-2 text-lg font-semibold ${ok ? "text-emerald-400" : "text-rose-400"}`}>
        {ok ? "Operational" : "Down"}
      </p>
      {component.detail && (
        <p className="mt-1 truncate text-xs text-slate-500" title={component.detail}>
          {component.detail}
        </p>
      )}
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch("/api/backend/health", { cache: "no-store" });
      const body: HealthResponse = await response.json();
      setHealth(body);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    } finally {
      setLastUpdated(new Date());
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const timer = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchHealth]);

  const overallOk = !unreachable && health?.status === "ok";

  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <header className="mb-10">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">QuantLab</h1>
          {health && (
            <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-400">
              v{health.version} · {health.environment}
            </span>
          )}
        </div>
        <p className="mt-2 text-slate-400">
          Quantitative research laboratory — system status
        </p>
      </header>

      <section className="mb-8 flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <StatusDot ok={overallOk} />
        <span className="text-lg font-semibold">
          {unreachable
            ? "Backend unreachable"
            : overallOk
              ? "All systems operational"
              : health
                ? "Degraded"
                : "Connecting…"}
        </span>
        {lastUpdated && (
          <span className="ml-auto text-xs text-slate-500">
            Updated {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {health ? (
          Object.entries(health.components).map(([name, component]) => (
            <ComponentCard key={name} name={name} component={component} />
          ))
        ) : (
          ["api", "database", "redis"].map((name) => (
            <div
              key={name}
              className="h-28 animate-pulse rounded-xl border border-slate-800 bg-slate-900/40"
            />
          ))
        )}
      </section>
    </main>
  );
}
