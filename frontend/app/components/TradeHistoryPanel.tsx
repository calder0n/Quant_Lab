"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

type TradeRecord = {
  id: string;
  executed_at: string | null;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  action: string;
  source: string;
  units: number;
  entry_price: number | null;
  exit_price: number | null;
  sl_price: number | null;
  tp_price: number | null;
  trailing_distance: number | null;
  realized_pl: number | null;
  order_id: string;
  filled: boolean;
  detail: string | null;
  signal_time: string | null;
  broker_trade_id: string | null;
  params: Record<string, number | string | boolean>;
};

const ACTION_STYLES: Record<string, string> = {
  opened_long: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  opened_short: "border-rose-500/30 bg-rose-500/10 text-rose-400",
  closed: "border-slate-500/30 bg-slate-500/10 text-slate-400",
};

const ACTION_LABELS: Record<string, string> = {
  opened_long: "▲ long",
  opened_short: "▼ short",
  closed: "✕ cierre",
};

const num = (v: number | null, digits = 2) => (v == null ? "—" : v.toFixed(digits));

type CompletedTrade = TradeRecord & {
  close: TradeRecord | null;
  realizedPl: number | null;
};

function completedTrades(records: TradeRecord[]): CompletedTrade[] {
  const closesByTrade = new Map<string, TradeRecord[]>();
  const closes: TradeRecord[] = [];
  for (const record of records) {
    if (record.action !== "closed") continue;
    closes.push(record);
    if (record.broker_trade_id) {
      closesByTrade.set(record.broker_trade_id, [...(closesByTrade.get(record.broker_trade_id) ?? []), record]);
    }
  }
  const opens = records
    .filter((record) => record.action === "opened_long" || record.action === "opened_short")
  const openIds = new Set(opens.map((record) => record.broker_trade_id).filter(Boolean));
  const result: CompletedTrade[] = opens
    .map((open) => {
      const closes = open.broker_trade_id ? closesByTrade.get(open.broker_trade_id) ?? [] : [];
      const close = closes[0] ?? null;
      return {
        ...open,
        close,
        realizedPl: closes.length ? closes.reduce((sum, item) => sum + (item.realized_pl ?? 0), 0) : null,
      };
    });
  // Older records may not have a broker trade id. Keep their close and its
  // broker P/L visible instead of silently dropping it from the audit trail.
  const unpairedCloses = closes.filter((close) => !close.broker_trade_id || !openIds.has(close.broker_trade_id));
  return [...result, ...unpairedCloses.map((close) => ({ ...close, close, realizedPl: close.realized_pl }))].sort(
    (a, b) => (b.close?.executed_at ?? b.executed_at ?? "").localeCompare(a.close?.executed_at ?? a.executed_at ?? ""),
  );
}

export default function TradeHistoryPanel() {
  const [records, setRecords] = useState<TradeRecord[] | null>(null);
  const [strategyFilter, setStrategyFilter] = useState("all");

  const refresh = useCallback(async () => {
    try {
      const response = await apiFetch("/trading/history?limit=200", { cache: "no-store" });
      if (response.ok) setRecords(await response.json());
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const trades = completedTrades(records ?? []);
  const strategies = Array.from(new Set(trades.map((r) => r.strategy_id))).sort();
  const visible = trades.filter(
    (r) => strategyFilter === "all" || r.strategy_id === strategyFilter,
  );

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-xl font-semibold">Trade history</h2>
        <span className="text-xs text-slate-500">
          operaciones completas: entrada, cierre real del broker y P&amp;L realizado
        </span>
        {strategies.length > 1 && (
          <select
            className="ml-auto rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
          >
            <option value="all">Todas las estrategias</option>
            {strategies.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {records === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : visible.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">
            Aún no hay operaciones registradas. Se guardará cada ejecución del auto-trader y del
            trading manual a partir de ahora.
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2.5">Cierre (UTC)</th>
                <th className="px-3 py-2.5">Estrategia</th>
                <th className="px-3 py-2.5">Mercado</th>
                <th className="px-3 py-2.5">Dirección</th>
                <th className="px-3 py-2.5 text-right">Units</th>
                <th className="px-3 py-2.5 text-right">Entrada</th>
                <th className="px-3 py-2.5 text-right">Salida</th>
                <th className="px-3 py-2.5 text-right">SL</th>
                <th className="px-3 py-2.5 text-right">TP</th>
                <th className="px-3 py-2.5 text-right">P/L</th>
                <th className="px-3 py-2.5">Origen</th>
                <th className="px-3 py-2.5">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {visible.map((r) => {
                const close = r.close;
                const exitPrice = close?.exit_price ?? close?.entry_price ?? r.exit_price;
                const closeReason = close?.detail ?? r.detail;
                return (
                <tr
                  key={r.id}
                  className="hover:bg-slate-800/30"
                  title={`Señal: ${r.signal_time ?? "—"} · Orden #${r.order_id}\nParámetros: ${Object.entries(
                    r.params,
                  )
                    .map(([k, v]) => `${k}=${typeof v === "number" ? Number(v.toFixed(4)) : v}`)
                    .join(", ")}`}
                >
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-slate-400">
                    {(close?.executed_at ?? r.executed_at)?.slice(0, 16).replace("T", " ") ?? "—"}
                  </td>
                  <td className="px-3 py-2 font-medium">{r.strategy_id}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-400">
                    {r.symbol} · {r.timeframe}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 ${
                        ACTION_STYLES[r.action] ?? ACTION_STYLES.closed
                      }`}
                    >
                      {r.action === "closed" ? "—" : ACTION_LABELS[r.action] ?? r.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.units}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.entry_price, 3)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(exitPrice, 3)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-rose-400/90">
                    {r.trailing_distance != null && r.action !== "closed"
                      ? `trail ${num(r.trailing_distance, 1)}`
                      : num(r.sl_price, 3)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-emerald-400/90">
                    {num(r.tp_price, 3)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums ${
                      r.realizedPl == null
                        ? "text-slate-500"
                        : r.realizedPl >= 0
                          ? "text-emerald-400"
                          : "text-rose-400"
                    }`}
                  >
                    {num(r.realizedPl)}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{r.source}</td>
                  <td className="max-w-40 truncate px-3 py-2 text-slate-500" title={r.detail ?? ""}>
                    {close ? closeReason || "closed" : r.action === "closed" ? closeReason || "closed" : "open"}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <p className="mt-2 text-[11px] text-slate-600">
        Pasa el cursor sobre una fila para ver la vela de señal, el nº de orden y los parámetros
        completos de la estrategia en ese momento.
      </p>
    </section>
  );
}
