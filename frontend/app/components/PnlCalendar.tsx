"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";

const MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];
const WEEKDAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fmt = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`;

export default function PnlCalendar() {
  const [pnl, setPnl] = useState<Record<string, number>>({});
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth()); // 0-11

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/trading/pnl-daily", { cache: "no-store" });
      if (res.ok) setPnl(await res.json());
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [refresh]);

  // A fixed 6-week grid starting on the Sunday on/before the 1st, so every
  // month lays out identically; days outside the month render dimmed.
  const cells = useMemo(() => {
    const start = new Date(year, month, 1);
    start.setDate(start.getDate() - start.getDay());
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [year, month]);

  const monthTotal = useMemo(
    () =>
      cells
        .filter((d) => d.getMonth() === month)
        .reduce((sum, d) => sum + (pnl[iso(d)] ?? 0), 0),
    [cells, pnl, month],
  );

  const todayIso = iso(now);
  const move = (delta: number) => {
    const d = new Date(year, month + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth());
  };

  const navBtn =
    "rounded-md border border-slate-700 px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200";

  return (
    <section className="mt-10">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">Calendario P&amp;L</h2>
        <span className="text-xs text-slate-500">P/L realizado por día (UTC)</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-slate-400">
            Mes:{" "}
            <span
              className={`font-semibold tabular-nums ${
                monthTotal > 0 ? "text-emerald-400" : monthTotal < 0 ? "text-rose-400" : "text-slate-400"
              }`}
            >
              {fmt(monthTotal)}
            </span>
          </span>
          <div className="flex items-center gap-1.5">
            <button onClick={() => move(-1)} className={navBtn} aria-label="Mes anterior">
              ‹
            </button>
            <span className="min-w-36 text-center text-sm font-medium">
              {MONTHS[month]} {year}
            </span>
            <button onClick={() => move(1)} className={navBtn} aria-label="Mes siguiente">
              ›
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
        <div className="grid grid-cols-7 border-b border-slate-800 text-center text-[11px] uppercase tracking-wide text-slate-500">
          {WEEKDAYS.map((w) => (
            <div key={w} className="py-2">
              {w}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {cells.map((d, i) => {
            const inMonth = d.getMonth() === month;
            const key = iso(d);
            const value = pnl[key];
            const isToday = key === todayIso;
            const tone =
              value == null
                ? ""
                : value > 0
                  ? "bg-emerald-500/15 text-emerald-300"
                  : value < 0
                    ? "bg-rose-500/15 text-rose-300"
                    : "";
            return (
              <div
                key={i}
                className={`relative flex min-h-20 flex-col border-b border-r border-slate-800/70 p-1.5 ${
                  inMonth ? "" : "opacity-35"
                } ${tone}`}
                title={value != null ? `${key}: ${fmt(value)}` : key}
              >
                <span
                  className={`self-end text-xs tabular-nums ${
                    isToday
                      ? "flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 font-semibold text-white"
                      : "text-slate-500"
                  }`}
                >
                  {d.getDate()}
                </span>
                {value != null && (
                  <span
                    className={`mt-auto pb-0.5 text-center text-sm font-semibold tabular-nums ${
                      value > 0 ? "text-emerald-400" : value < 0 ? "text-rose-400" : "text-slate-400"
                    }`}
                  >
                    {fmt(value)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-slate-600">
        Suma del P/L realizado de las operaciones cerradas ese día (incluye cierres por TP/SL/trailing
        del broker). Verde = ganancia, rojo = pérdida.
      </p>
    </section>
  );
}
