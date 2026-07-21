"use client";

import { useEffect, useState } from "react";

/** Info button that opens a modal explaining a section: what it is, how to use
 *  it and how to interpret what it shows. Content is passed as JSX children. */
export default function InfoModal({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Información de esta sección"
        className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300 transition hover:bg-[var(--accent-soft)] hover:text-[var(--accent-hover)]"
      >
        <span className="flex h-4 w-4 items-center justify-center rounded-full border border-current text-[10px] font-bold">
          i
        </span>
        Información
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:p-8"
          onClick={() => setOpen(false)}
        >
          <div
            className="my-8 w-full max-w-2xl rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <h3 className="text-lg font-bold">{title}</h3>
              <button
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-1 text-slate-400 transition hover:bg-white/5 hover:text-slate-200"
              >
                ✕
              </button>
            </div>
            <div className="info-body max-h-[70vh] overflow-y-auto px-6 py-5 text-sm leading-relaxed text-slate-300">
              {children}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** Sub-header inside the modal body ("Qué es", "Cómo se usa", …). */
export function InfoH({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-2 mt-5 text-[13px] font-bold uppercase tracking-wide text-[var(--accent-hover)] first:mt-0">
      {children}
    </h4>
  );
}

/** Term + definition row used for metric/field glossaries. */
export function InfoTerm({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <p className="mb-1.5">
      <span className="font-semibold text-slate-100">{term}</span>
      <span className="text-slate-400"> — {children}</span>
    </p>
  );
}
