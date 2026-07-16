"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

import SendToAutoTrader from "./SendToAutoTrader";

type StrategyOption = { strategy_id: string; name: string };
type DatasetOption = { symbol: string; timeframe: string; status: string };

type Study = {
  id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  optimizer: string;
  status: "pending" | "running" | "completed" | "failed";
  n_trials: number;
  trials_completed: number;
  best_score: number | null;
  message: string | null;
  created_at: string | null;
};

type Trial = {
  number: number;
  score: number;
  params: Record<string, number | string | boolean>;
  metrics: {
    profit_factor: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    trades: number;
    total_return: number;
  };
};

type Workers = { online: boolean; jobs_ongoing: number; queued: number };

const STATUS_STYLES: Record<Study["status"], string> = {
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  running: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  pending: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  failed: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};

export default function OptimizationsPanel() {
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [studies, setStudies] = useState<Study[] | null>(null);
  const [workers, setWorkers] = useState<Workers | null>(null);
  const [strategyId, setStrategyId] = useState("");
  const [dataset, setDataset] = useState("");
  const [optimizer, setOptimizer] = useState("optuna");
  const [trials, setTrials] = useState(200);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [topTrials, setTopTrials] = useState<Record<string, Trial[]>>({});

  useEffect(() => {
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyOption[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => undefined);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [studiesRes, workersRes, datasetsRes] = await Promise.all([
        apiFetch("/optimizations", { cache: "no-store" }),
        apiFetch("/workers", { cache: "no-store" }),
        apiFetch("/datasets", { cache: "no-store" }),
      ]);
      if (studiesRes.ok) setStudies(await studiesRes.json());
      if (workersRes.ok) setWorkers(await workersRes.json());
      if (datasetsRes.ok) {
        const ready = (await datasetsRes.json()).filter(
          (d: DatasetOption) => d.status === "ready",
        );
        setDatasets(ready);
        setDataset((current) =>
          current || (ready.length > 0 ? `${ready[0].symbol}|${ready[0].timeframe}` : ""),
        );
      }
    } catch {
      // backend unreachable: keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  const launch = async () => {
    if (!strategyId || !dataset) return;
    const [symbol, timeframe] = dataset.split("|");
    setLaunching(true);
    setError(null);
    try {
      const response = await apiFetch("/optimizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          symbol,
          timeframe,
          optimizer,
          n_trials: trials,
        }),
      });
      const body = await response.json();
      if (!response.ok) setError(body.detail ?? "Launch failed");
      refresh();
    } catch {
      setError("Backend unreachable");
    } finally {
      setLaunching(false);
    }
  };

  const toggleTrials = async (studyId: string) => {
    if (expanded === studyId) {
      setExpanded(null);
      return;
    }
    setExpanded(studyId);
    try {
      const response = await apiFetch(`/optimizations/${studyId}/trials?limit=10`, {
        cache: "no-store",
      });
      if (response.ok) setTopTrials((prev) => ({ ...prev, [studyId]: [] }));
      const body = await response.json();
      if (response.ok) setTopTrials((prev) => ({ ...prev, [studyId]: body }));
    } catch {
      // ignore
    }
  };

  const inputClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-xl font-semibold">Optimization</h2>
        {workers && (
          <span
            className={`rounded-full border px-2 py-0.5 text-xs ${
              workers.online
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                : "border-rose-500/30 bg-rose-500/15 text-rose-400"
            }`}
          >
            {workers.online
              ? `workers online · ${workers.jobs_ongoing} running · ${workers.queued} queued`
              : "workers offline"}
          </span>
        )}
      </div>

      <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Strategy
            <select
              className={inputClass}
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
            >
              {strategies.map((s) => (
                <option key={s.strategy_id} value={s.strategy_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Dataset
            <select
              className={inputClass}
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
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Optimizer
            <select
              className={inputClass}
              value={optimizer}
              onChange={(e) => setOptimizer(e.target.value)}
            >
              <option value="optuna">Optuna (TPE)</option>
              <option value="random">Random search</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Trials
            <input
              type="number"
              min={5}
              max={100000}
              className={`${inputClass} w-24`}
              value={trials}
              onChange={(e) => setTrials(Number(e.target.value))}
            />
          </label>
          <button
            onClick={launch}
            disabled={launching || !strategyId || !dataset || !workers?.online}
            title={workers?.online ? undefined : "Start the worker container first"}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {launching ? "Launching…" : "Launch study"}
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {studies === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : studies.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">
            No studies yet. Launch one to start exploring parameter space.
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3">Optimizer</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Progress</th>
                <th className="px-4 py-3 text-right">Best score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {studies.map((study) => (
                <Fragment key={study.id}>
                  <tr
                    onClick={() => toggleTrials(study.id)}
                    className="cursor-pointer hover:bg-slate-800/30"
                    title={study.message ?? "Click to see top trials"}
                  >
                    <td className="px-4 py-2.5 font-medium">{study.strategy_id}</td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {study.symbol} · {study.timeframe}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">{study.optimizer}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-block rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLES[study.status]}`}
                      >
                        {study.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">
                      {study.trials_completed.toLocaleString()} /{" "}
                      {study.n_trials.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {study.best_score === null ? "—" : study.best_score.toFixed(4)}
                    </td>
                  </tr>
                  {expanded === study.id && (
                    <tr>
                      <td colSpan={6} className="bg-slate-950/40 px-6 py-3">
                        {!topTrials[study.id] || topTrials[study.id].length === 0 ? (
                          <p className="text-xs text-slate-500">No trials recorded yet.</p>
                        ) : (
                          <table className="w-full text-xs">
                            <thead className="text-slate-500">
                              <tr>
                                <th className="py-1 text-left">#</th>
                                <th className="py-1 text-right">Score</th>
                                <th className="py-1 text-right">Return</th>
                                <th className="py-1 text-right">PF</th>
                                <th className="py-1 text-right">Sharpe</th>
                                <th className="py-1 text-right">MaxDD</th>
                                <th className="py-1 text-right">Win%</th>
                                <th className="py-1 text-right">Trades</th>
                                <th className="py-1 pl-4 text-left">Params</th>
                                <th className="py-1"></th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/40">
                              {topTrials[study.id].map((trial) => (
                                <tr key={trial.number} className="text-slate-300">
                                  <td className="py-1">{trial.number}</td>
                                  <td className="py-1 text-right tabular-nums font-medium text-emerald-400">
                                    {trial.score.toFixed(4)}
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {(trial.metrics.total_return * 100).toFixed(1)}%
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {trial.metrics.profit_factor.toFixed(2)}
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {trial.metrics.sharpe.toFixed(2)}
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {(trial.metrics.max_drawdown * 100).toFixed(1)}%
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {(trial.metrics.win_rate * 100).toFixed(0)}%
                                  </td>
                                  <td className="py-1 text-right tabular-nums">
                                    {trial.metrics.trades}
                                  </td>
                                  <td
                                    className="max-w-md truncate py-1 pl-4 text-slate-500"
                                    title={JSON.stringify(trial.params)}
                                  >
                                    {Object.entries(trial.params)
                                      .map(([k, v]) =>
                                        `${k}=${typeof v === "number" ? Number(v.toFixed(3)) : v}`,
                                      )
                                      .join(" ")}
                                  </td>
                                  <td className="py-1 pl-3 text-right">
                                    <SendToAutoTrader
                                      strategyId={study.strategy_id}
                                      symbol={study.symbol}
                                      timeframe={study.timeframe}
                                      params={trial.params}
                                    />
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
