"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

import PlotlyChart from "./PlotlyChart";

type HeatmapCell = { symbol: string; timeframe: string; best_score: number; studies: number };

type RankingEntry = {
  study_id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  trial_number: number;
  score: number;
  params: Record<string, number | string | boolean>;
  metrics: {
    total_return: number;
    profit_factor: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    trades: number;
  };
};

const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

export default function ResultsPanel() {
  const [cells, setCells] = useState<HeatmapCell[]>([]);
  const [ranking, setRanking] = useState<RankingEntry[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [heatmapRes, rankingRes] = await Promise.all([
        apiFetch("/results/heatmap", { cache: "no-store" }),
        apiFetch("/results/ranking?limit=10", { cache: "no-store" }),
      ]);
      if (heatmapRes.ok) setCells(await heatmapRes.json());
      if (rankingRes.ok) setRanking(await rankingRes.json());
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const symbols = [...new Set(cells.map((c) => c.symbol))].sort();
  const z = symbols.map((symbol) =>
    TIMEFRAMES.map((tf) => {
      const cell = cells.find((c) => c.symbol === symbol && c.timeframe === tf);
      return cell ? cell.best_score : null;
    }),
  );

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Results</h2>
        <span className="text-xs text-slate-500">
          best optimization score per market · global trial ranking
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 lg:col-span-2">
          <p className="mb-2 text-xs uppercase text-slate-500">Edge heatmap</p>
          {symbols.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">
              Run optimization studies to populate the heatmap.
            </p>
          ) : (
            <PlotlyChart
              data={[
                {
                  x: TIMEFRAMES,
                  y: symbols,
                  z,
                  type: "heatmap",
                  colorscale: [
                    [0, "#7f1d1d"],
                    [0.5, "#1e293b"],
                    [1, "#065f46"],
                  ],
                  zmid: 0,
                  hoverongaps: false,
                  hovertemplate: "%{y} %{x}<br>best score %{z:.4f}<extra></extra>",
                  colorbar: { thickness: 8, outlinewidth: 0, tickfont: { size: 9 } },
                },
              ]}
              layout={{ margin: { t: 8, r: 8, b: 28, l: 64 } }}
              height={Math.max(200, symbols.length * 36 + 60)}
            />
          )}
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 lg:col-span-3">
          <p className="px-4 pt-4 text-xs uppercase text-slate-500">Top trials (all studies)</p>
          {ranking === null || ranking.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">No completed studies yet.</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="px-4 py-2">#</th>
                  <th className="px-4 py-2">Strategy</th>
                  <th className="px-4 py-2">Dataset</th>
                  <th className="px-4 py-2 text-right">Score</th>
                  <th className="px-4 py-2 text-right">Return</th>
                  <th className="px-4 py-2 text-right">PF</th>
                  <th className="px-4 py-2 text-right">Sharpe</th>
                  <th className="px-4 py-2 text-right">MaxDD</th>
                  <th className="px-4 py-2 text-right">Trades</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {ranking.map((entry, index) => (
                  <tr
                    key={`${entry.study_id}-${entry.trial_number}`}
                    title={JSON.stringify(entry.params)}
                    className="hover:bg-slate-800/30"
                  >
                    <td className="px-4 py-2 text-slate-500">{index + 1}</td>
                    <td className="px-4 py-2 font-medium">{entry.strategy_id}</td>
                    <td className="px-4 py-2 text-slate-400">
                      {entry.symbol} · {entry.timeframe}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-emerald-400">
                      {entry.score.toFixed(4)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {(entry.metrics.total_return * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {entry.metrics.profit_factor.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {entry.metrics.sharpe.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {(entry.metrics.max_drawdown * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{entry.metrics.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
