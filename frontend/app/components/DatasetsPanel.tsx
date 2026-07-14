"use client";

import { useCallback, useEffect, useState } from "react";

type Dataset = {
  id: string;
  symbol: string;
  timeframe: string;
  status: "pending" | "syncing" | "ready" | "error";
  candle_count: number;
  start_at: string | null;
  end_at: string | null;
  source: string;
  message: string | null;
};

const POLL_INTERVAL_MS = 5000;

const STATUS_STYLES: Record<Dataset["status"], string> = {
  ready: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  syncing: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  pending: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  error: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toISOString().slice(0, 16).replace("T", " ");
}

export default function DatasetsPanel() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const fetchDatasets = useCallback(async () => {
    try {
      const response = await fetch("/api/backend/datasets", { cache: "no-store" });
      if (response.ok) setDatasets(await response.json());
    } catch {
      // backend unreachable: keep last known state
    }
  }, []);

  useEffect(() => {
    fetchDatasets();
    const timer = setInterval(fetchDatasets, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchDatasets]);

  const triggerSync = useCallback(async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const response = await fetch("/api/backend/datasets/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const body = await response.json();
      setSyncMessage(
        response.status === 202
          ? `Sync scheduled for ${body.pairs} series`
          : (body.detail ?? "Sync request failed"),
      );
      fetchDatasets();
    } catch {
      setSyncMessage("Backend unreachable");
    } finally {
      setSyncing(false);
    }
  }, [fetchDatasets]);

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Datasets</h2>
        <div className="flex items-center gap-3">
          {syncMessage && <span className="text-xs text-slate-400">{syncMessage}</span>}
          <button
            onClick={triggerSync}
            disabled={syncing}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-1.5 text-sm font-medium text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
          >
            {syncing ? "Scheduling…" : "Sync history"}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {datasets === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : datasets.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">
            No datasets yet. Configure QL_OANDA_API_TOKEN and press “Sync history”.
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">TF</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Candles</th>
                <th className="px-4 py-3">From</th>
                <th className="px-4 py-3">To</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {datasets.map((dataset) => (
                <tr key={dataset.id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 font-medium">{dataset.symbol}</td>
                  <td className="px-4 py-2.5 text-slate-400">{dataset.timeframe}</td>
                  <td className="px-4 py-2.5">
                    <span
                      title={dataset.message ?? undefined}
                      className={`inline-block rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLES[dataset.status]}`}
                    >
                      {dataset.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {dataset.candle_count.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400">{formatDate(dataset.start_at)}</td>
                  <td className="px-4 py-2.5 text-slate-400">{formatDate(dataset.end_at)}</td>
                  <td className="px-4 py-2.5 text-slate-500">{dataset.source || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
