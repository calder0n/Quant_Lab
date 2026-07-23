"use client";

import { useCallback, useEffect, useState } from "react";

import AutoTradersPanel from "./components/AutoTradersPanel";
import BacktestPanel from "./components/BacktestPanel";
import BrokerSettingsPanel from "./components/BrokerSettingsPanel";
import DatasetsPanel from "./components/DatasetsPanel";
import LoginGate from "./components/LoginGate";
import LogsPanel from "./components/LogsPanel";
import MlPanel from "./components/MlPanel";
import PnlCalendar from "./components/PnlCalendar";
import OptimizationsPanel from "./components/OptimizationsPanel";
import ResultsPanel from "./components/ResultsPanel";
import StrategiesPanel from "./components/StrategiesPanel";
import TradeHistoryPanel from "./components/TradeHistoryPanel";
import TradingPanel from "./components/TradingPanel";
import ValidationsPanel from "./components/ValidationsPanel";
import { SectionInfoButton } from "./components/sectionInfo";
import { apiFetch, getToken, setToken } from "./lib/api";

type ComponentStatus = { status: "ok" | "error"; detail: string | null };

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

type MenuId =
  | "overview"
  | "data"
  | "strategies"
  | "backtest"
  | "optimize"
  | "ml"
  | "trading"
  | "logs"
  | "settings";

const MENUS: { id: MenuId; label: string }[] = [
  { id: "overview", label: "Resumen" },
  { id: "data", label: "Datos" },
  { id: "strategies", label: "Estrategias" },
  { id: "backtest", label: "Backtest" },
  { id: "optimize", label: "Optimización" },
  { id: "ml", label: "ML" },
  { id: "trading", label: "Trading" },
  { id: "logs", label: "Logs" },
  { id: "settings", label: "Ajustes" },
];

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      {ok && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
      )}
      <span
        className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
          ok ? "bg-emerald-400" : "bg-rose-500"
        }`}
      />
    </span>
  );
}

function ComponentCard({ name, component }: { name: string; component: ComponentStatus }) {
  const ok = component.status === "ok";
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">{COMPONENT_LABELS[name] ?? name}</h3>
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

function Overview({
  health,
  unreachable,
  lastUpdated,
}: {
  health: HealthResponse | null;
  unreachable: boolean;
  lastUpdated: Date | null;
}) {
  const overallOk = !unreachable && health?.status === "ok";
  return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <h2 className="text-2xl font-bold tracking-tight">Resumen del sistema</h2>
      </div>

      <section className="mb-6 flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--panel)] p-5">
        <StatusDot ok={overallOk} />
        <span className="text-lg font-semibold">
          {unreachable
            ? "Backend inalcanzable"
            : overallOk
              ? "Todos los sistemas operativos"
              : health
                ? "Degradado"
                : "Conectando…"}
        </span>
        {lastUpdated && (
          <span className="ml-auto text-xs text-slate-500">
            Actualizado {lastUpdated.toLocaleTimeString()}
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
              className="h-28 animate-pulse rounded-xl border border-[var(--border)] bg-[var(--panel)]/40"
            />
          ))
        )}
      </section>
    </div>
  );
}

function UserMenu() {
  const [me, setMe] = useState<{ username: string; role: string } | null>(null);

  useEffect(() => {
    if (!getToken()) return;
    apiFetch("/auth/me", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => undefined);
  }, []);

  if (!getToken()) return null;
  return (
    <div className="flex items-center gap-3 text-xs text-slate-400">
      {me && (
        <span className="hidden sm:inline">
          {me.username} · <span className="uppercase text-slate-500">{me.role}</span>
        </span>
      )}
      <button
        onClick={() => setToken(null)}
        className="rounded-md border border-[var(--border)] px-2.5 py-1 text-slate-300 transition hover:bg-white/5"
      >
        Salir
      </button>
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [active, setActive] = useState<MenuId>("overview");

  useEffect(() => {
    const saved = window.localStorage.getItem("ql.menu") as MenuId | null;
    if (saved && MENUS.some((m) => m.id === saved)) setActive(saved);
  }, []);

  const selectMenu = useCallback((id: MenuId) => {
    setActive(id);
    window.localStorage.setItem("ql.menu", id);
  }, []);

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
  const isLive = health?.environment === "live";

  return (
    <LoginGate>
      {/* Top navigation bar */}
      <header className="sticky top-0 z-30 border-b border-[var(--border)] bg-[var(--bg)]/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent)] text-sm font-black text-white">
              Q
            </span>
            <span className="text-lg font-bold tracking-tight">QuantLab</span>
            {health && (
              <span
                className={`ml-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                  isLive
                    ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
                    : "border-slate-600/40 bg-white/5 text-slate-400"
                }`}
              >
                v{health.version} · {health.environment}
              </span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div className="hidden items-center gap-2 text-xs text-slate-400 sm:flex">
              <StatusDot ok={overallOk} />
              {unreachable ? "Sin conexión" : overallOk ? "Operativo" : "Degradado"}
            </div>
            <UserMenu />
          </div>
        </div>

        {/* Category pills = menus */}
        <nav className="mx-auto max-w-6xl px-4">
          <div className="no-scrollbar flex gap-1 overflow-x-auto pb-2">
            {MENUS.map((menu) => {
              const isActive = active === menu.id;
              return (
                <button
                  key={menu.id}
                  onClick={() => selectMenu(menu.id)}
                  className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
                    isActive
                      ? "bg-[var(--accent-soft)] text-[var(--accent-hover)]"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  }`}
                >
                  {menu.label}
                </button>
              );
            })}
          </div>
        </nav>
      </header>

      {/* Content area — one section at a time; drop the panels' leading margin */}
      <main className="mx-auto max-w-6xl px-6 py-8 [&>div>section:first-child]:mt-0 [&_section]:mt-0 [&_section]:mb-8">
        <div className="mb-4 flex justify-end">
          <SectionInfoButton menu={active} />
        </div>
        {active === "overview" && (
          <Overview health={health} unreachable={unreachable} lastUpdated={lastUpdated} />
        )}
        {active === "data" && <DatasetsPanel />}
        {active === "strategies" && <StrategiesPanel />}
        {active === "backtest" && (
          <>
            <BacktestPanel />
            <ResultsPanel />
          </>
        )}
        {active === "optimize" && (
          <>
            <OptimizationsPanel />
            <ValidationsPanel />
          </>
        )}
        {active === "ml" && <MlPanel />}
        {active === "trading" && (
          <>
            <TradingPanel />
            <AutoTradersPanel />
            <PnlCalendar />
            <TradeHistoryPanel />
          </>
        )}
        {active === "logs" && <LogsPanel />}
        {active === "settings" && <BrokerSettingsPanel />}
      </main>
    </LoginGate>
  );
}
