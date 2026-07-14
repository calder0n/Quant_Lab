"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

type StrategyOption = { strategy_id: string; name: string };
type DatasetOption = { symbol: string; timeframe: string; status: string };

type ValidationRun = {
  id: string;
  kind: "walk_forward" | "monte_carlo" | "stress";
  strategy_id: string;
  symbol: string;
  timeframe: string;
  status: "pending" | "running" | "completed" | "failed";
  result: Record<string, unknown> | null;
  message: string | null;
};

const KIND_LABELS: Record<ValidationRun["kind"], string> = {
  walk_forward: "Walk-Forward",
  monte_carlo: "Monte Carlo",
  stress: "Stress test",
};

const STATUS_STYLES: Record<ValidationRun["status"], string> = {
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  running: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  pending: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  failed: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};

const pct = (v: unknown) => `${((v as number) * 100).toFixed(1)}%`;
const num = (v: unknown) => (v as number).toFixed(3);

function ResultSummary({ run }: { run: ValidationRun }) {
  const r = run.result;
  if (!r) return <p className="text-xs text-slate-500">{run.message ?? "No result."}</p>;

  if (run.kind === "walk_forward") {
    const folds = (r.folds as Record<string, unknown>[]) ?? [];
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-4 text-xs">
          <Stat label="WF efficiency" value={num(r.wf_efficiency)} highlight />
          <Stat label="Mean IS score" value={num(r.mean_is_score)} />
          <Stat label="Mean OOS score" value={num(r.mean_oos_score)} />
          <Stat label="OOS return" value={pct(r.oos_total_return)} />
          <Stat label="OOS folds > 0" value={`${r.positive_oos_folds}/${r.n_folds}`} />
          <Stat label="OOS trades" value={String(r.oos_trades)} />
        </div>
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 text-left">Fold</th>
              <th className="py-1 text-left">Test window</th>
              <th className="py-1 text-right">IS score</th>
              <th className="py-1 text-right">OOS score</th>
              <th className="py-1 text-right">OOS return</th>
              <th className="py-1 text-right">OOS trades</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/40 text-slate-300">
            {folds.map((fold) => {
              const oos = fold.oos_metrics as Record<string, number>;
              return (
                <tr key={String(fold.fold)}>
                  <td className="py-1">{String(fold.fold)}</td>
                  <td className="py-1 text-slate-500">
                    {String(fold.test_start).slice(0, 10)} → {String(fold.test_end).slice(0, 10)}
                  </td>
                  <td className="py-1 text-right tabular-nums">{num(fold.is_score)}</td>
                  <td
                    className={`py-1 text-right tabular-nums ${
                      (fold.oos_score as number) > 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {num(fold.oos_score)}
                  </td>
                  <td className="py-1 text-right tabular-nums">{pct(oos.total_return)}</td>
                  <td className="py-1 text-right tabular-nums">{oos.trades}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  if (run.kind === "monte_carlo") {
    return (
      <div className="flex flex-wrap gap-4 text-xs">
        <Stat label="Runs" value={String(r.n_runs)} />
        <Stat label="Trades" value={String(r.n_trades)} />
        <Stat label="Return p5" value={pct(r.final_return_p5)} />
        <Stat label="Return p50" value={pct(r.final_return_p50)} highlight />
        <Stat label="Return p95" value={pct(r.final_return_p95)} />
        <Stat label="MaxDD p50" value={pct(r.max_drawdown_p50)} />
        <Stat label="MaxDD p95" value={pct(r.max_drawdown_p95)} />
        <Stat label="P(loss)" value={pct(r.prob_loss)} />
        <Stat label="P(ruin)" value={pct(r.prob_ruin)} />
      </div>
    );
  }

  const scenarios = (r.scenarios as Record<string, unknown>[]) ?? [];
  return (
    <div className="space-y-3">
      <div className="flex gap-4 text-xs">
        <Stat
          label="Profitable under stress"
          value={`${r.profitable_scenarios}/${r.total_scenarios}`}
          highlight
        />
      </div>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 text-left">Scenario</th>
            <th className="py-1 text-right">Return</th>
            <th className="py-1 text-right">Degradation</th>
            <th className="py-1 text-right">PF</th>
            <th className="py-1 text-right">MaxDD</th>
            <th className="py-1 text-right">Trades</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/40 text-slate-300">
          {scenarios.map((scenario) => {
            const m = scenario.metrics as Record<string, number>;
            return (
              <tr key={String(scenario.name)}>
                <td className="py-1">{String(scenario.name)}</td>
                <td
                  className={`py-1 text-right tabular-nums ${
                    m.total_return > 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {pct(m.total_return)}
                </td>
                <td className="py-1 text-right tabular-nums">{pct(scenario.return_degradation)}</td>
                <td className="py-1 text-right tabular-nums">{m.profit_factor.toFixed(2)}</td>
                <td className="py-1 text-right tabular-nums">{pct(m.max_drawdown)}</td>
                <td className="py-1 text-right tabular-nums">{m.trades}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
      <p className="text-slate-500">{label}</p>
      <p
        className={`mt-0.5 font-semibold tabular-nums ${
          highlight ? "text-emerald-400" : "text-slate-200"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

export default function ValidationsPanel() {
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [runs, setRuns] = useState<ValidationRun[] | null>(null);
  const [kind, setKind] = useState<ValidationRun["kind"]>("walk_forward");
  const [strategyId, setStrategyId] = useState("");
  const [dataset, setDataset] = useState("");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/backend/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyOption[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => undefined);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [runsRes, datasetsRes] = await Promise.all([
        fetch("/api/backend/validations", { cache: "no-store" }),
        fetch("/api/backend/datasets", { cache: "no-store" }),
      ]);
      if (runsRes.ok) setRuns(await runsRes.json());
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
      // keep last state
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
      const response = await fetch("/api/backend/validations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, strategy_id: strategyId, symbol, timeframe, config: {} }),
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

  const selectClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Validation</h2>
        <span className="text-xs text-slate-500">
          never trust an in-sample winner — validate it
        </span>
      </div>

      <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Method
            <select
              className={selectClass}
              value={kind}
              onChange={(e) => setKind(e.target.value as ValidationRun["kind"])}
            >
              <option value="walk_forward">Walk-Forward (optimize IS, test OOS)</option>
              <option value="monte_carlo">Monte Carlo (trade resampling)</option>
              <option value="stress">Stress test (hostile costs + delay)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Strategy
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
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Dataset
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
          </label>
          <button
            onClick={launch}
            disabled={launching || !strategyId || !dataset}
            className="rounded-lg border border-violet-700 bg-violet-600/20 px-4 py-1.5 text-sm font-medium text-violet-300 transition hover:bg-violet-600/30 disabled:opacity-40"
          >
            {launching ? "Launching…" : "Launch validation"}
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
        <p className="mt-3 text-xs text-slate-500">
          Defaults: WF = 5 folds · 70% train · 30 trials (optuna). Monte Carlo = 1000 runs.
          Stress = 6 hostile scenarios. Monte Carlo and stress use the strategy&apos;s default
          params unless provided via API.
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {runs === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : runs.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">No validations yet.</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Method</th>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Key result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {runs.map((run) => (
                <Fragment key={run.id}>
                  <tr
                    onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                    className="cursor-pointer hover:bg-slate-800/30"
                    title={run.message ?? "Click for details"}
                  >
                    <td className="px-4 py-2.5 font-medium">{KIND_LABELS[run.kind]}</td>
                    <td className="px-4 py-2.5 text-slate-400">{run.strategy_id}</td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {run.symbol} · {run.timeframe}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-block rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLES[run.status]}`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-300">
                      {run.result
                        ? run.kind === "walk_forward"
                          ? `WF eff ${num(run.result.wf_efficiency)}`
                          : run.kind === "monte_carlo"
                            ? `p50 ${pct(run.result.final_return_p50)} · P(loss) ${pct(run.result.prob_loss)}`
                            : `${run.result.profitable_scenarios}/${run.result.total_scenarios} survive`
                        : "—"}
                    </td>
                  </tr>
                  {expanded === run.id && (
                    <tr>
                      <td colSpan={5} className="bg-slate-950/40 px-6 py-4">
                        <ResultSummary run={run} />
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
