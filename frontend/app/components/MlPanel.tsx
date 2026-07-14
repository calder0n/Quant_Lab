"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

type DatasetOption = { symbol: string; timeframe: string; status: string };

type MlModel = {
  id: string;
  kind: "ml" | "rl";
  target: string;
  algorithm: string;
  symbol: string;
  timeframe: string;
  status: "pending" | "running" | "completed" | "failed";
  metrics: Record<string, unknown> | null;
  message: string | null;
};

const ML_ALGORITHMS = ["xgboost", "lightgbm", "catboost", "torch_mlp"];
const TARGETS = [
  { value: "win", label: "win — P(TP first)" },
  { value: "sl_hit", label: "sl_hit — P(SL first)" },
  { value: "tp_hit", label: "tp_hit — P(TP touched)" },
  { value: "expected_move", label: "expected_move (regression)" },
];

const STATUS_STYLES: Record<MlModel["status"], string> = {
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  running: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  pending: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  failed: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};

function keyMetric(model: MlModel): string {
  const m = model.metrics;
  if (!m) return "—";
  if (model.kind === "rl") {
    return `eval ${(((m.eval_total_return as number) ?? 0) * 100).toFixed(1)}% · ${m.eval_trades} trades`;
  }
  if (m.task === "classification") {
    return `AUC ${(m.auc as number).toFixed(3)} (base ${((m.base_rate as number) * 100).toFixed(0)}%)`;
  }
  return `R² ${(m.r2 as number).toFixed(3)} · MAE ${(m.mae as number).toExponential(2)}`;
}

function MetricsDetail({ model }: { model: MlModel }) {
  const m = model.metrics;
  if (!m) return <p className="text-xs text-slate-500">{model.message ?? "No metrics."}</p>;
  const importances = (m.feature_importances as Record<string, number>) ?? {};
  const top = Object.entries(importances).slice(0, 8);
  return (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap gap-3">
        {Object.entries(m)
          .filter(([k, v]) => typeof v === "number")
          .map(([k, v]) => (
            <div key={k} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
              <p className="text-slate-500">{k}</p>
              <p className="mt-0.5 font-semibold tabular-nums text-slate-200">
                {Number.isInteger(v) ? String(v) : (v as number).toFixed(4)}
              </p>
            </div>
          ))}
      </div>
      {top.length > 0 && (
        <div>
          <p className="mb-1 text-slate-500">Top features</p>
          <div className="flex flex-wrap gap-2">
            {top.map(([name, weight]) => (
              <span
                key={name}
                className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-slate-300"
              >
                {name} · {(weight * 100).toFixed(1)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function MlPanel() {
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [models, setModels] = useState<MlModel[] | null>(null);
  const [kind, setKind] = useState<"ml" | "rl">("ml");
  const [target, setTarget] = useState("win");
  const [algorithm, setAlgorithm] = useState("xgboost");
  const [dataset, setDataset] = useState("");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [modelsRes, datasetsRes] = await Promise.all([
        fetch("/api/backend/ml/models", { cache: "no-store" }),
        fetch("/api/backend/datasets", { cache: "no-store" }),
      ]);
      if (modelsRes.ok) setModels(await modelsRes.json());
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
    if (!dataset) return;
    const [symbol, timeframe] = dataset.split("|");
    setLaunching(true);
    setError(null);
    try {
      const response = await fetch("/api/backend/ml/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          target: kind === "ml" ? target : "policy",
          algorithm: kind === "ml" ? algorithm : "ppo",
          symbol,
          timeframe,
          config: {},
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

  const selectClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Machine Learning</h2>
        <span className="text-xs text-slate-500">
          trade-outcome models (triple-barrier) and RL policies (PPO)
        </span>
      </div>

      <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Kind
            <select
              className={selectClass}
              value={kind}
              onChange={(e) => setKind(e.target.value as "ml" | "rl")}
            >
              <option value="ml">Supervised ML</option>
              <option value="rl">Reinforcement Learning</option>
            </select>
          </label>
          {kind === "ml" && (
            <>
              <label className="flex flex-col gap-1 text-xs text-slate-400">
                Target
                <select
                  className={selectClass}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  {TARGETS.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-400">
                Algorithm
                <select
                  className={selectClass}
                  value={algorithm}
                  onChange={(e) => setAlgorithm(e.target.value)}
                >
                  {ML_ALGORITHMS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {kind === "rl" && (
            <span className="pb-2 text-xs text-slate-500">PPO · MlpPolicy · 20k timesteps</span>
          )}
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
            disabled={launching || !dataset}
            className="rounded-lg border border-amber-700 bg-amber-600/20 px-4 py-1.5 text-sm font-medium text-amber-300 transition hover:bg-amber-600/30 disabled:opacity-40"
          >
            {launching ? "Launching…" : "Train model"}
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {models === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : models.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">No models yet.</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Kind</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Algorithm</th>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Key metric</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {models.map((model) => (
                <Fragment key={model.id}>
                  <tr
                    onClick={() => setExpanded(expanded === model.id ? null : model.id)}
                    className="cursor-pointer hover:bg-slate-800/30"
                    title={model.message ?? "Click for details"}
                  >
                    <td className="px-4 py-2.5 font-medium uppercase">{model.kind}</td>
                    <td className="px-4 py-2.5 text-slate-400">{model.target}</td>
                    <td className="px-4 py-2.5 text-slate-400">{model.algorithm}</td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {model.symbol} · {model.timeframe}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-block rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLES[model.status]}`}
                      >
                        {model.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-300">{keyMetric(model)}</td>
                  </tr>
                  {expanded === model.id && (
                    <tr>
                      <td colSpan={6} className="bg-slate-950/40 px-6 py-4">
                        <MetricsDetail model={model} />
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
