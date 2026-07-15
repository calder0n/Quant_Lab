"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";

import PlotlyChart from "./PlotlyChart";

type ParamSpec = {
  name: string;
  kind: "int" | "float" | "bool" | "categorical";
  default: number | boolean | string;
  low: number | null;
  high: number | null;
  step: number | null;
  choices: string[] | null;
  group: string;
};

const PARAM_GROUPS: { key: string; label: string }[] = [
  { key: "strategy", label: "Strategy parameters" },
  { key: "risk", label: "Risk & exits" },
  { key: "filter", label: "Entry filters — enable/disable each" },
];

type StrategyInfo = {
  strategy_id: string;
  name: string;
  description: string;
  parameters: ParamSpec[];
};

type DatasetOption = { symbol: string; timeframe: string; status: string };

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
type Marker = { time: string; price: number };
type Chart = {
  time: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  overlays: Record<string, (number | null)[]>;
  markers: Record<string, Marker[]>;
};

type ParamValue = number | boolean | string;
type BacktestResponse = {
  fitness: number;
  metrics: Metrics;
  equity: EquityPoint[];
  trade_returns: number[];
  chart: Chart | null;
  params: Record<string, ParamValue>;
};

const OVERLAY_COLORS = ["#38bdf8", "#a78bfa", "#fbbf24", "#f472b6", "#22d3ee", "#a3e635"];

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

function defaultParams(strategy: StrategyInfo | undefined): Record<string, ParamValue> {
  if (!strategy) return {};
  return Object.fromEntries(strategy.parameters.map((p) => [p.name, p.default]));
}

function ParamField({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: ParamValue;
  onChange: (v: ParamValue) => void;
}) {
  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200";
  const hint =
    spec.kind === "int" || spec.kind === "float"
      ? `${spec.low ?? "−∞"} … ${spec.high ?? "∞"}`
      : spec.kind === "bool"
        ? "on / off"
        : (spec.choices ?? []).join(" · ");

  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[11px] text-slate-400">{spec.name}</span>
      {spec.kind === "bool" ? (
        <button
          type="button"
          onClick={() => onChange(!(value as boolean))}
          className={`rounded-md border px-2 py-1 text-sm transition ${
            value
              ? "border-emerald-600 bg-emerald-600/20 text-emerald-300"
              : "border-slate-700 bg-slate-800 text-slate-400"
          }`}
        >
          {value ? "true" : "false"}
        </button>
      ) : spec.kind === "categorical" ? (
        <select
          className={inputClass}
          value={value as string}
          onChange={(e) => onChange(e.target.value)}
        >
          {(spec.choices ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="number"
          className={inputClass}
          value={value as number}
          min={spec.low ?? undefined}
          max={spec.high ?? undefined}
          step={spec.kind === "int" ? 1 : (spec.step ?? "any")}
          onChange={(e) => onChange(spec.kind === "int" ? Math.round(+e.target.value) : +e.target.value)}
        />
      )}
      <span className="text-[10px] text-slate-600">{hint}</span>
    </label>
  );
}

export default function BacktestPanel() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [dataset, setDataset] = useState("");
  const [params, setParams] = useState<Record<string, ParamValue>>({});
  const [showParams, setShowParams] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  const strategy = useMemo(
    () => strategies.find((s) => s.strategy_id === strategyId),
    [strategies, strategyId],
  );

  useEffect(() => {
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyInfo[]) => {
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

  // Reset the editable parameters to the strategy's declared defaults on switch.
  useEffect(() => {
    setParams(defaultParams(strategy));
  }, [strategy]);

  const setParam = useCallback((name: string, value: ParamValue) => {
    setParams((prev) => ({ ...prev, [name]: value }));
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
        body: JSON.stringify({ strategy_id: strategyId, symbol, timeframe, params, chart_bars: 400 }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Backtest failed");
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

  const priceTraces = useMemo(() => {
    if (!result?.chart) return [];
    const c = result.chart;
    const traces: unknown[] = [
      {
        type: "candlestick",
        x: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        name: "price",
        increasing: { line: { color: "#34d399", width: 1 } },
        decreasing: { line: { color: "#fb7185", width: 1 } },
        showlegend: false,
      },
    ];
    Object.entries(c.overlays).forEach(([name, values], i) => {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: c.time,
        y: values,
        name,
        connectgaps: false,
        line: { color: OVERLAY_COLORS[i % OVERLAY_COLORS.length], width: 1.3 },
      });
    });
    const markerTrace = (
      key: string,
      name: string,
      symbol: string,
      color: string,
      yshift: number,
    ) => {
      const pts = c.markers[key] ?? [];
      if (pts.length === 0) return null;
      return {
        type: "scatter",
        mode: "markers",
        x: pts.map((p) => p.time),
        y: pts.map((p) => p.price * (1 + yshift)),
        name,
        marker: { symbol, color, size: 9, line: { color: "#0b1120", width: 1 } },
        hovertemplate: `${name} @ %{y:.5f}<extra></extra>`,
      };
    };
    const longEntry = markerTrace("long_entry", "long entry", "triangle-up", "#34d399", -0.001);
    const shortEntry = markerTrace("short_entry", "short entry", "triangle-down", "#fb7185", 0.001);
    const exits = [...(c.markers.long_exit ?? []), ...(c.markers.short_exit ?? [])];
    const exitTrace =
      exits.length > 0
        ? {
            type: "scatter",
            mode: "markers",
            x: exits.map((p) => p.time),
            y: exits.map((p) => p.price),
            name: "exit",
            marker: { symbol: "x", color: "#94a3b8", size: 6 },
            hovertemplate: "exit @ %{y:.5f}<extra></extra>",
          }
        : null;
    return [...traces, longEntry, shortEntry, exitTrace].filter(Boolean);
  }, [result]);

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
          <select className={selectClass} value={dataset} onChange={(e) => setDataset(e.target.value)}>
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

        {strategy && (
          <p className="mt-3 text-xs text-slate-500">{strategy.description}</p>
        )}

        {/* Parameter editor */}
        {strategy && (
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40">
            <button
              onClick={() => setShowParams((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-400 hover:text-slate-200"
            >
              <span>Parameters &amp; filters · {strategy.parameters.length}</span>
              <span className="flex items-center gap-3">
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    setParams(defaultParams(strategy));
                  }}
                  className="rounded border border-slate-700 px-2 py-0.5 text-[10px] normal-case text-slate-400 hover:bg-slate-800"
                >
                  Reset defaults
                </span>
                <span className="text-slate-600">{showParams ? "▲" : "▼"}</span>
              </span>
            </button>
            {showParams && (
              <div className="border-t border-slate-800 p-4">
                {PARAM_GROUPS.map(({ key, label }) => {
                  const specs = strategy.parameters.filter((p) => (p.group ?? "strategy") === key);
                  if (specs.length === 0) return null;
                  return (
                    <div key={key} className="mb-4 last:mb-0">
                      <p
                        className={`mb-2 font-mono text-[10px] uppercase tracking-wider ${
                          key === "filter" ? "text-sky-400" : "text-slate-500"
                        }`}
                      >
                        {label}
                      </p>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
                        {specs.map((spec) => (
                          <ParamField
                            key={spec.name}
                            spec={spec}
                            value={params[spec.name] ?? spec.default}
                            onChange={(v) => setParam(spec.name, v)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
        {datasets.length === 0 && !error && (
          <p className="mt-3 text-xs text-slate-500">Sync a dataset first to run a backtest.</p>
        )}

        {result && (
          <>
            {/* Price + strategy logic (last 400 bars) */}
            {result.chart && result.chart.time.length > 0 && (
              <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">
                  Price &amp; entry logic — last {result.chart.time.length} bars (indicators/filters
                  used by the strategy, with ▲ long / ▼ short entries and ✕ exits)
                </p>
                <PlotlyChart
                  data={priceTraces}
                  layout={{
                    xaxis: { type: "category", nticks: 8, rangeslider: { visible: false } },
                    showlegend: true,
                    legend: { orientation: "h", y: 1.04, x: 0, font: { size: 10 } },
                    margin: { t: 30, r: 12, b: 30, l: 56 },
                  }}
                  height={420}
                />
              </div>
            )}

            {/* Metrics */}
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {METRIC_VIEW.map(({ key, label, fmt }) => (
                <div key={key} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-sm font-semibold tabular-nums">{fmt(result.metrics[key])}</p>
                </div>
              ))}
            </div>

            {/* Equity + drawdown */}
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

            {/* Trade distribution */}
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
