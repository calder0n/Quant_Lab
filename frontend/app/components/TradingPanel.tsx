"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

type StrategyOption = { strategy_id: string; name: string };

type Position = { symbol: string; units: number; average_price: number; unrealized_pl: number };

type TradingStatus = {
  enabled: boolean;
  environment: "practice" | "live";
  account: {
    account_id: string;
    currency: string;
    balance: number;
    nav: number;
    margin_available: number;
  } | null;
  positions: Position[];
  detail: string | null;
};

type ExecutionResult = {
  action: string;
  symbol: string;
  signal_time: string;
  orders: { instrument: string; units: number; filled: boolean; detail: string }[];
};

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "NAS100", "SPX500", "US30"];
const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

export default function TradingPanel() {
  const [status, setStatus] = useState<TradingStatus | null>(null);
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("H1");
  const [units, setUnits] = useState(1000);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [lastExecution, setLastExecution] = useState<ExecutionResult | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await apiFetch("/trading/status", { cache: "no-store" });
      if (response.ok) setStatus(await response.json());
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyOption[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => undefined);
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const toggle = async () => {
    if (!status) return;
    setBusy(true);
    setMessage(null);
    try {
      const response = await apiFetch("/trading/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: !status.enabled,
          confirm: confirmText.trim() || null,
        }),
      });
      const body = await response.json();
      if (!response.ok) setMessage({ ok: false, text: body.detail ?? "Toggle failed" });
      else {
        setStatus(body);
        setConfirmText("");
        setMessage({
          ok: true,
          text: body.enabled ? "Trading ENABLED" : "Trading disabled (kill switch off)",
        });
      }
    } catch {
      setMessage({ ok: false, text: "Backend unreachable" });
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    setBusy(true);
    setMessage(null);
    setLastExecution(null);
    try {
      const response = await apiFetch("/trading/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, symbol, timeframe, units }),
      });
      const body = await response.json();
      if (!response.ok) setMessage({ ok: false, text: body.detail ?? "Execution failed" });
      else {
        setLastExecution(body);
        setMessage({ ok: true, text: `Signal evaluated: ${body.action}` });
        refresh();
      }
    } catch {
      setMessage({ ok: false, text: "Backend unreachable" });
    } finally {
      setBusy(false);
    }
  };

  const inputClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";
  const isLive = status?.environment === "live";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-xl font-semibold">Trading</h2>
        {status && (
          <>
            <span
              className={`rounded-full border px-2 py-0.5 text-xs ${
                status.enabled
                  ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                  : "border-slate-500/30 bg-slate-500/15 text-slate-400"
              }`}
            >
              {status.enabled ? "ENABLED" : "disabled"}
            </span>
            <span
              className={`rounded-full border px-2 py-0.5 text-xs ${
                isLive
                  ? "border-rose-500/30 bg-rose-500/15 text-rose-400"
                  : "border-sky-500/30 bg-sky-500/15 text-sky-400"
              }`}
            >
              {status.environment}
            </span>
          </>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        {status?.detail && <p className="mb-3 text-sm text-amber-400">{status.detail}</p>}

        {status?.account && (
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Balance" value={`${status.account.balance.toFixed(2)} ${status.account.currency}`} />
            <Stat label="NAV" value={status.account.nav.toFixed(2)} />
            <Stat label="Margin available" value={status.account.margin_available.toFixed(2)} />
            <Stat label="Open positions" value={String(status.positions.length)} />
          </div>
        )}

        {status && status.positions.length > 0 && (
          <table className="mb-4 w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Instrument</th>
                <th className="py-1 text-right">Units</th>
                <th className="py-1 text-right">Avg price</th>
                <th className="py-1 text-right">Unrealized P/L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40 text-slate-300">
              {status.positions.map((position) => (
                <tr key={position.symbol}>
                  <td className="py-1">{position.symbol}</td>
                  <td className="py-1 text-right tabular-nums">{position.units}</td>
                  <td className="py-1 text-right tabular-nums">{position.average_price}</td>
                  <td
                    className={`py-1 text-right tabular-nums ${
                      position.unrealized_pl >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {position.unrealized_pl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <span className="text-xs text-slate-400">
            Kill switch — trading stays off until an admin enables it.
            {isLive && (
              <span className="ml-1 font-semibold text-rose-400">
                LIVE environment: enabling requires typing TRADE-LIVE.
              </span>
            )}
          </span>
          {isLive && !status?.enabled && (
            <input
              className={`${inputClass} w-36`}
              placeholder="TRADE-LIVE"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
            />
          )}
          <button
            onClick={toggle}
            disabled={busy || !status}
            className={`rounded-lg border px-4 py-1.5 text-sm font-medium transition disabled:opacity-40 ${
              status?.enabled
                ? "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
                : "border-rose-700 bg-rose-600/20 text-rose-300 hover:bg-rose-600/30"
            }`}
          >
            {status?.enabled ? "Disable trading" : "Enable trading"}
          </button>
        </div>

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
              className={`${inputClass} w-28`}
              value={units}
              onChange={(e) => setUnits(Number(e.target.value))}
            />
          </label>
          <button
            onClick={execute}
            disabled={busy || !status?.enabled || !strategyId}
            title={status?.enabled ? undefined : "Enable trading first"}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {busy ? "Working…" : "Evaluate & execute signal"}
          </button>
        </div>

        {message && (
          <p className={`mt-3 text-sm ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>
            {message.text}
          </p>
        )}
        {lastExecution && (
          <p className="mt-1 text-xs text-slate-500">
            {lastExecution.action} · signal bar {lastExecution.signal_time} ·{" "}
            {lastExecution.orders.map((o) => `${o.instrument} ${o.units} (${o.detail})`).join(", ") ||
              "no orders"}
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Executes the latest closed-bar signal of a strategy using fresh broker candles, with
          SL/TP from the strategy&apos;s order plan. Validate any strategy (walk-forward, stress,
          Monte Carlo) before trading it, and prefer the practice environment.
        </p>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-200">{value}</p>
    </div>
  );
}
