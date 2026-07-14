"use client";

import { useEffect, useState } from "react";

export type StrategyInfo = {
  strategy_id: string;
  name: string;
  category: string;
  description: string;
  parameters: { name: string; kind: string; default: unknown }[];
};

const CATEGORY_STYLES: Record<string, string> = {
  trend: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  mean_reversion: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  breakout: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  smc: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
};

export default function StrategiesPanel() {
  const [strategies, setStrategies] = useState<StrategyInfo[] | null>(null);

  useEffect(() => {
    fetch("/api/backend/strategies", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then(setStrategies)
      .catch(() => setStrategies(null));
  }, []);

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Strategies</h2>
        {strategies && (
          <span className="text-xs text-slate-500">{strategies.length} plugins discovered</span>
        )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {strategies === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3 text-right">Params</th>
                <th className="px-4 py-3">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {strategies.map((strategy) => (
                <tr key={strategy.strategy_id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 font-medium">{strategy.name}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-xs ${
                        CATEGORY_STYLES[strategy.category] ??
                        "bg-slate-500/15 text-slate-400 border-slate-500/30"
                      }`}
                    >
                      {strategy.category}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">
                    {strategy.parameters.length}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400">{strategy.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
