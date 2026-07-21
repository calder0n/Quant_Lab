"use client";

import { useState } from "react";

import { apiFetch } from "../lib/api";

type ParamValue = number | string | boolean;

// Metals/indices trade in small unit counts; FX in thousands.
const SMALL_UNIT_SYMBOLS = new Set(["XAUUSD", "NAS100", "SPX500", "US30"]);

/** Button that creates a (disabled) auto-trader assignment from a known
 *  strategy + market + parameter set. The user enables it later in the
 *  Automated trading panel — nothing trades from here. */
export default function SendToAutoTrader({
  strategyId,
  symbol,
  timeframe,
  params,
}: {
  strategyId: string;
  symbol: string;
  timeframe: string;
  params: Record<string, ParamValue>;
}) {
  const [open, setOpen] = useState(false);
  const [units, setUnits] = useState(SMALL_UNIT_SYMBOLS.has(symbol) ? 1 : 1000);
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  const send = async () => {
    setState("busy");
    try {
      const res = await apiFetch("/autotraders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, symbol, timeframe, units, params }),
      });
      const body = await res.json();
      if (!res.ok) {
        setState("error");
        setMsg(typeof body.detail === "string" ? body.detail : "Failed");
      } else {
        setState("done");
        setOpen(false);
      }
    } catch {
      setState("error");
      setMsg("Backend unreachable");
    }
  };

  if (state === "done") {
    return <span className="text-xs text-emerald-400">✓ sent (disabled)</span>;
  }

  const btn =
    "rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-sky-400";

  return (
    <span className="inline-flex items-center gap-1.5">
      {!open ? (
        <button onClick={() => setOpen(true)} className={btn} title="Create an auto-trader assignment">
          → Auto-trader
        </button>
      ) : (
        <span className="inline-flex items-center gap-1">
          <input
            type="number"
            min={1}
            value={units}
            onChange={(e) => setUnits(Number(e.target.value))}
            className="w-16 rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200"
            title="units"
          />
          <button
            onClick={send}
            disabled={state === "busy"}
            className="rounded border border-emerald-700 bg-emerald-600/20 px-2 py-0.5 text-xs text-emerald-300 hover:bg-emerald-600/30 disabled:opacity-40"
          >
            Add
          </button>
          <button onClick={() => setOpen(false)} className={btn}>
            ✕
          </button>
        </span>
      )}
      {state === "error" && <span className="text-xs text-rose-400">{msg}</span>}
    </span>
  );
}
