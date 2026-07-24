"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

type StrategyOption = { strategy_id: string; name: string };

type AutoTrader = {
  id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  units: number;
  params: Record<string, number | string | boolean>;
  ml_model_id: string | null;
  invert: boolean;
  realized_pl: number;
  enabled: boolean;
  last_run: string | null;
  last_signal_time: string | null;
  last_action: string | null;
  message: string | null;
};

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "NAS100", "SPX500", "US30"];
const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

const ACTION_STYLES: Record<string, string> = {
  opened_long: "text-emerald-400",
  opened_short: "text-rose-400",
  closed: "text-amber-400",
  none: "text-slate-500",
};

export default function AutoTradersPanel() {
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [autotraders, setAutotraders] = useState<AutoTrader[] | null>(null);
  const [tradingOn, setTradingOn] = useState<boolean | null>(null);
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("H4");
  const [units, setUnits] = useState(1);
  const [paramsText, setParamsText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [listRes, statusRes] = await Promise.all([
        apiFetch("/autotraders", { cache: "no-store" }),
        apiFetch("/trading/status", { cache: "no-store" }),
      ]);
      if (listRes.ok) setAutotraders(await listRes.json());
      if (statusRes.ok) setTradingOn((await statusRes.json()).enabled);
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyOption[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => undefined);
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  const create = async () => {
    setBusy(true);
    setError(null);
    let params: unknown;
    try {
      params = JSON.parse(paramsText || "{}");
    } catch {
      setError("Params must be valid JSON");
      setBusy(false);
      return;
    }
    try {
      const response = await apiFetch("/autotraders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, symbol, timeframe, units, params }),
      });
      const body = await response.json();
      if (!response.ok) setError(typeof body.detail === "string" ? body.detail : "Create failed");
      refresh();
    } catch {
      setError("Backend unreachable");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (at: AutoTrader) => {
    await apiFetch(`/autotraders/${at.id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !at.enabled }),
    });
    refresh();
  };

  const toggleInvert = async (at: AutoTrader) => {
    await apiFetch(`/autotraders/${at.id}/invert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invert: !at.invert }),
    });
    refresh();
  };

  const remove = async (at: AutoTrader) => {
    await apiFetch(`/autotraders/${at.id}`, { method: "DELETE" });
    refresh();
  };

  const inputClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-xl font-semibold">Automated trading</h2>
        <span className="text-xs text-slate-500">
          a dedicated worker runs each enabled strategy on live OANDA data
        </span>
      </div>

      {tradingOn === false && (
        <p className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-300">
          The global kill switch is OFF — enabled assignments stay idle until you turn on trading in
          the Trading panel.
        </p>
      )}

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
            Symbol
            <select className={inputClass} value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {SYMBOLS.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Timeframe
            <select
              className={inputClass}
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf}>{tf}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Units
            <input
              type="number"
              min={1}
              className={`${inputClass} w-24`}
              value={units}
              onChange={(e) => setUnits(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs text-slate-400">
            Params (JSON — paste the tuned config)
            <input
              className={`${inputClass} w-full font-mono text-xs`}
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              placeholder='{"breakout_atr": 1.73}'
            />
          </label>
          <button
            onClick={create}
            disabled={busy || !strategyId}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/30 disabled:opacity-40"
          >
            Add assignment
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        {autotraders === null ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : autotraders.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">
            No assignments yet. Add one above (start disabled, then enable when ready).
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Market</th>
                <th className="px-4 py-3 text-right">Units</th>
                <th className="px-4 py-3">State</th>
                <th
                  className="px-4 py-3"
                  title="Operar al revés: si la estrategia dice comprar, vende (y viceversa)"
                >
                  Inversa
                </th>
                <th className="px-4 py-3 text-right" title="P/L realizado de las operaciones cerradas de esta estrategia">
                  P&amp;L
                </th>
                <th className="px-4 py-3">Last run</th>
                <th className="px-4 py-3">Last action</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {autotraders.map((at) => (
                <tr key={at.id} className="hover:bg-slate-800/30" title={at.message ?? undefined}>
                  <td className="px-4 py-2.5 font-medium" title={JSON.stringify(at.params)}>
                    {at.strategy_id}
                    {at.ml_model_id && (
                      <span
                        className="ml-1.5 rounded border border-violet-500/30 bg-violet-500/10 px-1 py-0.5 text-[9px] font-normal text-violet-300"
                        title={`Filtro ML activo · modelo ${at.ml_model_id.slice(0, 8)}`}
                      >
                        ML
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400">
                    {at.symbol} · {at.timeframe}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{at.units}</td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => toggle(at)}
                      className={`rounded-full border px-2 py-0.5 text-xs ${
                        at.enabled
                          ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                          : "border-slate-500/30 bg-slate-500/15 text-slate-400"
                      }`}
                    >
                      {at.enabled ? "enabled" : "disabled"}
                    </button>
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => toggleInvert(at)}
                      title={
                        at.invert
                          ? "Operando al revés — clic para volver a normal"
                          : "Operar normal — clic para invertir señales"
                      }
                      className={`rounded-full border px-2 py-0.5 text-xs ${
                        at.invert
                          ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                          : "border-slate-600/40 bg-slate-500/10 text-slate-500"
                      }`}
                    >
                      {at.invert ? "⇄ inversa" : "normal"}
                    </button>
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums ${
                      at.realized_pl > 0
                        ? "text-emerald-400"
                        : at.realized_pl < 0
                          ? "text-rose-400"
                          : "text-slate-500"
                    }`}
                    title="P/L realizado (operaciones cerradas)"
                  >
                    {at.realized_pl > 0 ? "+" : ""}
                    {at.realized_pl.toFixed(2)}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">
                    {at.last_run ? at.last_run.replace("T", " ").slice(0, 16) : "—"}
                  </td>
                  <td className={`px-4 py-2.5 text-xs ${ACTION_STYLES[at.last_action ?? "none"]}`}>
                    {at.message ? (
                      <span className="text-rose-400">{at.message.slice(0, 40)}</span>
                    ) : (
                      (at.last_action ?? "—")
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => remove(at)}
                      className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-rose-400"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
