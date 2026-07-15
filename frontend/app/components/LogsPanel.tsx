"use client";

import { useCallback, useEffect, useState } from "react";

type LogEntry = {
  time: string | null;
  level: string;
  source: string;
  logger: string;
  message: string;
};

const LEVEL_STYLES: Record<string, string> = {
  ERROR: "text-rose-400",
  WARNING: "text-amber-400",
  INFO: "text-slate-300",
};

export default function LogsPanel() {
  const [logs, setLogs] = useState<LogEntry[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/backend/logs?limit=80", { cache: "no-store" });
      if (response.ok) setLogs(await response.json());
    } catch {
      // keep last state
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Logs</h2>
        <span className="text-xs text-slate-500">API and workers, newest first</span>
      </div>
      <div className="max-h-80 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/70 p-3 font-mono text-xs leading-5">
        {logs === null ? (
          <p className="text-slate-500">Loading…</p>
        ) : logs.length === 0 ? (
          <p className="text-slate-500">No log entries yet — launch a sync, study or training.</p>
        ) : (
          logs.map((entry, index) => (
            <p key={index} className="whitespace-pre-wrap break-all">
              <span className="text-slate-600">
                {entry.time ? entry.time.replace("T", " ").slice(0, 19) : "—"}
              </span>{" "}
              <span
                className={
                  entry.source === "worker" ? "text-violet-400" : "text-sky-400"
                }
              >
                [{entry.source}]
              </span>{" "}
              <span className={LEVEL_STYLES[entry.level] ?? "text-slate-400"}>
                {entry.message}
              </span>
            </p>
          ))
        )}
      </div>
    </section>
  );
}
