"use client";

const TOKEN_KEY = "ql_token";
export const AUTH_CHANGED_EVENT = "ql-auth-changed";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

/** fetch against the backend API with the session token attached.
 *  A 401 clears the session and sends the user back to the login gate. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api/backend${path}`, { ...init, headers });
  if (response.status === 401 && token) setToken(null);
  return response;
}
