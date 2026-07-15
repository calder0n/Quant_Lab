"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

import PlotlyChart from "./PlotlyChart";

type DatasetOption = { symbol: string; timeframe: string; status: string };
type StrategyOption = { strategy_id: string; name: string };

type Metrics = {
  total_return: number;
  cagr: number;
  profit_factor: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown: number;
  recovery_factor: number;
  expectancy: number;
  win_rate: number;
  avg_trade_return: number;
  trades: number;
};

type EquityPoint = { time: string; value: number };
type BacktestResponse = {
  fitness: number;
  metrics: Metrics;
  equity: EquityPoint[];
  trade_returns: number[];
};

function drawdownSeries(equity: EquityPoint[]): number[] {
  let peak = -Infinity;
  return equity.map((point) => {
    peak = Math.max(peak, point.value);
    return peak > 0 ? (point.value / peak - 1) * 100 : 0;
  });
}

const pct = (value: number) => `${(value * 100).toFixed(2)}%`;
const num = (value: number) => value.toFixed(2);

const METRIC_VIEW: { key: keyof Metrics; label: string; fmt: (v: number) => string }[] = [
  { key: "total_return", label: "Total return", fmt: pct },
  { key: "cagr", label: "CAGR", fmt: pct },
  { key: "max_drawdown", label: "Max drawdown", fmt: pct },
  { key: "win_rate", label: "Win rate", fmt: pct },
  { key: "profit_factor", label: "Profit factor", fmt: num },
  { key: "sharpe", label: "Sharpe", fmt: num },
  { key: "sortino", label: "Sortino", fmt: num },
  { key: "calmar", label: "Calmar", fmt: num },
  { key: "recovery_factor", label: "Recovery", fmt: num },
  { key: "expectancy", label: "Expectancy", fmt: num },
  { key: "avg_trade_return", label: "Avg trade", fmt: pct },
  { key: "trades", label: "Trades", fmt: (v) => String(v) },
];

export default function BacktestPanel() {
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [dataset, setDataset] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  useEffect(() => {
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyOption[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => setStrategies([]));
    apiFetch("/datasets", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: DatasetOption[]) => {
        const ready = list.filter((d) => d.status === "ready");
        setDatasets(ready);
        if (ready.length > 0) setDataset(`${ready[0].symbol}|${ready[0].timeframe}`);
      })
      .catch(() => setDatasets([]));
  }, []);

  const runBacktest = async () => {
    if (!strategyId || !dataset) return;
    const [symbol, timeframe] = dataset.split("|");
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiFetch("/backtests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, symbol, timeframe }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.detail ?? "Backtest failed");
      } else {
        setResult(body);
      }
    } catch {
      setError("Backend unreachable");
    } finally {
      setRunning(false);
    }
  };

  const selectClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  return (
    <section className="mt-10">
      <h2 className="mb-4 text-xl font-semibold">Quick backtest</h2>
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <select
            className={selectClass}
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
          >
            {strategies.map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name}
              </option>
            ))}
          </select>
          <select
            className={selectClass}
            value={dataset}
            onChange={(e) => setDataset(e.target.value)}
          >
            {datasets.length === 0 ? (
              <option value="">No datasets ready</option>
            ) : (
              datasets.map((d) => (
                <option key={`${d.symbol}|${d.timeframe}`} value={`${d.symbol}|${d.timeframe}`}>
                  {d.symbol} · {d.timeframe}
                </option>
              ))
            )}
          </select>
          <button
            onClick={runBacktest}
            disabled={running || !strategyId || !dataset}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {running ? "Running…" : "Run backtest"}
          </button>
          {result && (
            <span className="ml-auto text-sm text-slate-400">
              Fitness:{" "}
              <span
                className={`font-semibold ${result.fitness >= 0 ? "text-emerald-400" : "text-rose-400"}`}
              >
                {result.fitness.toFixed(4)}
              </span>
            </span>
          )}
        </div>

        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
        {datasets.length === 0 && !error && (
          <p className="mt-3 text-xs text-slate-500">
            Sync a dataset first (default parameters are used for the quick run).
          </p>
        )}

        {result && (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {METRIC_VIEW.map(({ key, label, fmt }) => (
                <div key={key} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-sm font-semibold tabular-nums">
                    {fmt(result.metrics[key])}
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">Equity curve</p>
                <PlotlyChart
                  data={[
                    {
                      x: result.equity.map((p) => p.time),
                      y: result.equity.map((p) => p.value),
                      type: "scatter",
                      mode: "lines",
                      line: { color: "#34d399", width: 1.5 },
                      hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
                    },
                  ]}
                  height={240}
                />
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">Drawdown</p>
                <PlotlyChart
                  data={[
                    {
                      x: result.equity.map((p) => p.time),
                      y: drawdownSeries(result.equity),
                      type: "scatter",
                      mode: "lines",
                      fill: "tozeroy",
                      line: { color: "#fb7185", width: 1 },
                      fillcolor: "rgba(251,113,133,0.15)",
                      hovertemplate: "%{x}<br>%{y:.2f}%<extra></extra>",
                    },
                  ]}
                  layout={{ yaxis: { ticksuffix: "%" } }}
                  height={240}
                />
              </div>
            </div>
            {result.trade_returns.length > 0 && (
              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">
                  Trade return distribution ({result.trade_returns.length} trades)
                </p>
                <PlotlyChart
                  data={[
                    {
                      x: result.trade_returns.map((r) => r * 100),
                      type: "histogram",
                      nbinsx: 60,
                      marker: { color: "#38bdf8", opacity: 0.85 },
                      hovertemplate: "%{x:.2f}%: %{y} trades<extra></extra>",
                    },
                  ]}
                  layout={{ xaxis: { ticksuffix: "%" }, bargap: 0.05 }}
                  height={220}
                />
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
