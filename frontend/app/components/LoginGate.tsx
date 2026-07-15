"use client";

import { useCallback, useEffect, useState } from "react";

import { AUTH_CHANGED_EVENT, apiFetch, getToken, setToken } from "../lib/api";

type AuthStatus = { auth_enabled: boolean; initialized: boolean };
type Me = { username: string; role: string };

export default function LoginGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [hasToken, setHasToken] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setHasToken(getToken() !== null);
    try {
      const response = await fetch("/api/backend/auth/status", { cache: "no-store" });
      if (response.ok) setStatus(await response.json());
    } catch {
      setStatus(null);
    }
    if (getToken()) {
      const meResponse = await apiFetch("/auth/me", { cache: "no-store" });
      if (meResponse.ok) setMe(await meResponse.json());
    } else {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener(AUTH_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
  }, [refresh]);

  const submit = async (endpoint: "setup" | "login") => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/backend/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.detail?.[0]?.msg ?? body.detail ?? "Request failed");
      } else {
        setToken(body.access_token);
        setPassword("");
      }
    } catch {
      setError("Backend unreachable");
    } finally {
      setBusy(false);
    }
  };

  if (status === null) {
    return <p className="p-16 text-center text-sm text-slate-500">Connecting…</p>;
  }
  if (!status.auth_enabled) {
    return <>{children}</>;
  }

  if (!status.initialized || !hasToken) {
    const isSetup = !status.initialized;
    return (
      <div className="mx-auto mt-24 max-w-sm rounded-xl border border-slate-800 bg-slate-900/60 p-8">
        <h1 className="text-2xl font-bold">QuantLab</h1>
        <p className="mt-1 text-sm text-slate-400">
          {isSetup
            ? "First run: create the administrator account."
            : "Sign in to your research lab."}
        </p>
        <div className="mt-6 flex flex-col gap-3">
          <input
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm"
            placeholder="Username"
            value={username}
            autoComplete="username"
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm"
            placeholder={isSetup ? "Password (min 8 chars)" : "Password"}
            type="password"
            value={password}
            autoComplete={isSetup ? "new-password" : "current-password"}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit(isSetup ? "setup" : "login")}
          />
          <button
            onClick={() => submit(isSetup ? "setup" : "login")}
            disabled={busy || username.length < 3 || password.length < 8}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {busy ? "Working…" : isSetup ? "Create admin & sign in" : "Sign in"}
          </button>
          {error && <p className="text-sm text-rose-400">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="mb-2 flex items-center justify-end gap-3 text-xs text-slate-500">
        {me && (
          <span>
            {me.username} · <span className="uppercase">{me.role}</span>
          </span>
        )}
        <button
          onClick={() => setToken(null)}
          className="rounded border border-slate-700 px-2 py-0.5 hover:bg-slate-800"
        >
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
