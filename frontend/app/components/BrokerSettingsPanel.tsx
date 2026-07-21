"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

type BrokerSettings = {
  broker: string;
  configured: boolean;
  source: "database" | "environment" | "none";
  token_preview: string | null;
  account_id: string;
  environment: "practice" | "live";
};

type TestResult = { ok: boolean; detail: string; accounts: string[] };

const SOURCE_LABELS: Record<BrokerSettings["source"], string> = {
  database: "saved in portal",
  environment: "from environment (.env)",
  none: "not configured",
};

export default function BrokerSettingsPanel() {
  const [current, setCurrent] = useState<BrokerSettings | null>(null);
  const [token, setToken] = useState("");
  const [accountId, setAccountId] = useState("");
  const [environment, setEnvironment] = useState<"practice" | "live">("practice");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await apiFetch("/settings/broker", { cache: "no-store" });
      if (!response.ok) return;
      const body: BrokerSettings = await response.json();
      setCurrent(body);
      setAccountId(body.account_id);
      setEnvironment(body.environment);
    } catch {
      setCurrent(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const payload: Record<string, string> = { account_id: accountId, environment };
      if (token.trim()) payload.api_token = token.trim();
      const response = await apiFetch("/settings/broker", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) {
        setMessage({ ok: false, text: body.detail?.[0]?.msg ?? body.detail ?? "Save failed" });
      } else {
        setToken("");
        setCurrent(body);
        setMessage({ ok: true, text: "Credentials saved" });
      }
    } catch {
      setMessage({ ok: false, text: "Backend unreachable" });
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await apiFetch("/settings/broker/test", { method: "POST" });
      const body: TestResult = await response.json();
      const accounts = body.accounts.length > 0 ? ` Accounts: ${body.accounts.join(", ")}` : "";
      setMessage({ ok: body.ok, text: body.detail + (body.ok ? accounts : "") });
    } catch {
      setMessage({ ok: false, text: "Backend unreachable" });
    } finally {
      setBusy(false);
    }
  };

  const clearStored = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await apiFetch("/settings/broker", { method: "DELETE" });
      if (response.ok) {
        setCurrent(await response.json());
        setToken("");
        setMessage({ ok: true, text: "Portal credentials removed" });
      }
    } catch {
      setMessage({ ok: false, text: "Backend unreachable" });
    } finally {
      setBusy(false);
    }
  };

  const inputClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500";
  const buttonClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-4 py-1.5 text-sm font-medium text-slate-200 transition hover:bg-slate-700 disabled:opacity-40";

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-xl font-semibold">Broker settings</h2>
        {current && (
          <span
            className={`text-xs ${current.configured ? "text-emerald-400" : "text-slate-500"}`}
          >
            {current.configured
              ? `OANDA configured (${SOURCE_LABELS[current.source]}, token ${current.token_preview})`
              : "OANDA not configured"}
          </span>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            API token
            <input
              type="password"
              autoComplete="off"
              className={inputClass}
              placeholder={current?.token_preview ?? "OANDA API token"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Account ID
            <input
              type="text"
              autoComplete="off"
              className={inputClass}
              placeholder="001-004-1234567-001"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Environment
            <select
              className={inputClass}
              value={environment}
              onChange={(e) => setEnvironment(e.target.value as "practice" | "live")}
            >
              <option value="practice">practice (demo)</option>
              <option value="live">live</option>
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button className={buttonClass} onClick={save} disabled={busy}>
              Save
            </button>
            <button
              className={buttonClass}
              onClick={testConnection}
              disabled={busy || !current?.configured}
            >
              Test connection
            </button>
            {current?.source === "database" && (
              <button className={buttonClass} onClick={clearStored} disabled={busy}>
                Clear
              </button>
            )}
          </div>
        </div>

        {message && (
          <p className={`mt-3 text-sm ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>
            {message.text}
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          The token is stored in your local PostgreSQL and never displayed again — only the
          masked preview. Portal credentials override the QL_OANDA_* environment variables.
        </p>
      </div>
    </section>
  );
}
