"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "../lib/api";

import PlotlyChart from "./PlotlyChart";
import SendToAutoTrader from "./SendToAutoTrader";

type ParamSpec = {
  name: string;
  kind: "int" | "float" | "bool" | "categorical";
  default: number | boolean | string;
  low: number | null;
  high: number | null;
  step: number | null;
  choices: string[] | null;
  group: string;
};

const PARAM_GROUPS: { key: string; label: string }[] = [
  { key: "strategy", label: "Strategy parameters" },
  { key: "risk", label: "Risk & exits" },
  { key: "filter", label: "Entry filters — enable/disable each" },
];

/** Hover help for every known parameter (shared risk/filter params + each
 *  strategy plugin's own). Unknown names simply show no tooltip. */
const PARAM_DOCS: Record<string, string> = {
  // Risk & exits (shared)
  atr_period:
    "Nº de velas del ATR (volatilidad media). Un periodo corto reacciona rápido al mercado; uno largo da distancias más estables para SL/TP.",
  sl_atr:
    "Distancia del stop-loss en múltiplos de ATR. 2.0 = el stop se coloca a 2×ATR del precio de entrada. Más bajo = pérdidas pequeñas pero más salidas por ruido.",
  tp_atr:
    "Distancia del take-profit en múltiplos de ATR. Junto con sl_atr define el ratio riesgo:beneficio (tp 3 / sl 2 = 1.5:1).",
  sl_pips:
    "Stop-loss a distancia fija en pips (0 = desactivado, usa el modo ATR). Si lo activas, reemplaza a sl_atr. Pip por instrumento: XAUUSD 0.1 · EURUSD 0.0001 · USDJPY 0.01 · índices 1 punto.",
  tp_pips:
    "Take-profit a distancia fija en pips (0 = desactivado, usa el modo ATR). Si lo activas, reemplaza a tp_atr. Puedes mezclar: SL por ATR y TP por pips, o al revés.",
  use_trailing:
    "Convierte el stop-loss en un trailing stop: la distancia sl_atr (o sl_pips si está activo) sigue al precio cuando avanza a favor, protegiendo ganancias. El TP sigue fijo.",
  max_atr_days:
    "Tope opcional: limita las distancias de SL y TP a este múltiplo del ATR diario del día anterior (0 = sin tope). Evita objetivos más lejos de lo que el mercado se mueve en un día.",
  // Entry filters (shared)
  use_session_filter:
    "Solo permite entradas dentro de la franja horaria [session_start, session_end] (UTC). Útil para operar solo Londres/NY y evitar horas muertas.",
  session_start: "Hora UTC de inicio de la sesión permitida (0–23). Solo aplica si el filtro de sesión está activo.",
  session_end:
    "Hora UTC de fin de la sesión permitida. Si es menor que session_start, la franja cruza medianoche.",
  use_spread_filter:
    "Bloquea entradas cuando el spread se dispara respecto a su mediana reciente (noticias, roll-over). Evita pagar costes anómalos.",
  max_spread_mult:
    "Umbral del filtro de spread: se bloquea la entrada si el spread actual supera este múltiplo de su mediana de las últimas 500 velas.",
  use_trend_filter:
    "Filtro direccional: solo longs por encima de la EMA de tendencia y solo shorts por debajo. Alinea las entradas con la tendencia mayor.",
  trend_ema: "Periodo de la EMA usada como referencia de tendencia (típico: 200).",
  use_volatility_filter:
    "Bloquea entradas cuando la volatilidad (ATR/precio) es demasiado baja — mercados dormidos donde el coste fijo pesa más que el movimiento esperado.",
  min_atr_pct:
    "Umbral del filtro de volatilidad: ATR mínimo como fracción del precio (0.0005 = 0.05%) para permitir entrar.",
  use_ml_filter:
    "Filtro de meta-labeling: solo permite la entrada si un modelo ML entrenado predice P(ganar) ≥ ml_threshold. El modelo se elige arriba en 'Filtro ML'; sin modelo asignado, este filtro no hace nada.",
  ml_threshold:
    "Confianza mínima P(ganar) que el modelo debe dar para permitir la entrada. Ojo: calíbralo a la distribución del modelo — si se entrenó con TP lejano, su P(ganar) es baja y umbrales de 0.20-0.30 ya filtran mucho.",
  // Strategy-specific
  fast_period: "Periodo de la media/línea rápida. Cruzar por encima de la lenta genera la señal alcista.",
  slow_period: "Periodo de la media/línea lenta, la referencia de tendencia del cruce.",
  signal_period: "Periodo de la línea de señal del MACD; los cruces MACD/señal disparan las entradas.",
  zero_line_filter:
    "Si está activo, solo toma cruces MACD alcistas por encima de cero y bajistas por debajo — filtra señales contra-tendencia.",
  bb_period: "Periodo de la media de las Bandas de Bollinger.",
  bb_std:
    "Anchura de las bandas en desviaciones estándar. Menor = bandas estrechas, más señales de reversión; mayor = solo extremos.",
  rsi_period: "Periodo del RSI. Corto = oscilador nervioso con más señales; largo = más suave.",
  oversold: "Nivel de sobreventa del RSI: por debajo se considera rebote alcista probable.",
  overbought: "Nivel de sobrecompra del RSI: por encima se considera caída probable.",
  channel_period: "Nº de velas del canal Donchian: romper el máximo/mínimo de este periodo dispara la entrada.",
  lookback: "Ventana de velas para detectar el máximo/mínimo de referencia de la ruptura.",
  buffer_atr:
    "Margen extra (en ATR) que el precio debe superar más allá del nivel de ruptura antes de entrar. Reduce falsas rupturas.",
  exit_lookback: "Ventana del canal de salida: una ruptura del extremo contrario de este periodo cierra la posición.",
  breakout_atr: "Tamaño mínimo del movimiento (en ATR) para considerarlo ruptura válida.",
  range_bars:
    "Nº de velas iniciales del día (UTC) que forman el rango de apertura. Romper su máximo/mínimo dispara la entrada. Rango más largo = rupturas más fiables pero más tardías.",
  swing_strength:
    "Velas a cada lado necesarias para confirmar un swing high/low. Mayor = estructura más significativa pero confirmada más tarde.",
  min_gap_atr: "Tamaño mínimo del fair value gap (en ATR) para considerarlo operable.",
  validity_bars: "Nº de velas que un nivel (gap/zona) permanece válido antes de descartarse.",
  displacement_atr:
    "Tamaño mínimo (en ATR) de la vela de desplazamiento que valida la señal ICT.",
  killzone_start: "Hora UTC de inicio de la killzone ICT (franja donde se buscan las entradas).",
  killzone_end: "Hora UTC de fin de la killzone ICT.",
  min_wick_atr: "Longitud mínima de la mecha (en ATR) para validar el barrido de liquidez.",
  deviation_pct: "Desviación mínima del precio respecto al VWAP (en fracción) para entrar en reversión.",
  exit_at_vwap: "Si está activo, la posición se cierra cuando el precio vuelve al VWAP.",
  z_entry: "Z-score de entrada: nº de desviaciones estándar respecto a la media para abrir la reversión.",
  z_exit: "Z-score de salida: al volver el precio a esta distancia de la media, se cierra.",
  // Custom composite strategy
  combine:
    "Cómo votan los componentes activos para entrar: any = basta uno (más operaciones), majority = más de la mitad de acuerdo, all = todos a la vez (confluencia estricta, pocas señales).",
  rsi_oversold:
    "Nivel de sobreventa del componente RSI de la custom: por debajo de este valor el RSI genera señal de compra. Solo aplica si use_rsi está activado.",
  rsi_overbought:
    "Nivel de sobrecompra del componente RSI de la custom: por encima de este valor el RSI genera señal de venta. Solo aplica si use_rsi está activado.",
  ...Object.fromEntries(
    [
      ["ema_cross", "cruce de EMAs rápida/lenta (tendencia)"],
      ["macd", "cruces de MACD y línea de señal (momentum)"],
      ["rsi", "sobreventa/sobrecompra del RSI (reversión)"],
      ["bollinger", "toques de las Bandas de Bollinger (reversión)"],
      ["mean_reversion", "z-score sobre la media (reversión estadística)"],
      ["vwap", "desviación respecto al VWAP (reversión intradía)"],
      ["donchian", "ruptura del canal Donchian (breakout)"],
      ["breakout", "ruptura de máximos/mínimos con buffer (breakout)"],
      ["atr_breakout", "movimientos mayores que N×ATR (breakout de volatilidad)"],
      ["opening_range", "ruptura del rango de apertura del día (breakout)"],
      ["smc", "estructura de mercado y BOS (Smart Money Concepts)"],
      ["fair_value_gap", "huecos de valor justo (SMC)"],
      ["order_blocks", "zonas de order blocks (SMC)"],
      ["liquidity_sweep", "barridos de liquidez con mecha (SMC)"],
      ["ict", "señales ICT dentro de la killzone horaria"],
    ].map(([id, what]) => [
      `use_${id}`,
      `Incluye las señales de ${id} — ${what} — en la estrategia combinada. El componente corre con sus parámetros por defecto.`,
    ]),
  ),
};

type StrategyInfo = {
  strategy_id: string;
  name: string;
  description: string;
  parameters: ParamSpec[];
};

type DatasetOption = { symbol: string; timeframe: string; status: string };
type ModelOption = {
  id: string;
  target: string;
  symbol: string;
  timeframe: string;
  status: string;
  config: Record<string, number | string | boolean>;
};
type StudyOption = {
  id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  status: string;
  best_score: number | null;
  best_params: Record<string, number | string | boolean> | null;
};

// Triple-barrier labeling defaults the ML trainer uses when a model's config
// omits them (see MlService._train_supervised).
const modelSl = (m: ModelOption) => Number(m.config?.sl_atr ?? 2.0);
const modelTp = (m: ModelOption) => Number(m.config?.tp_atr ?? 3.0);

type Metrics = {
  total_return: number;
  cagr: number;
  profit_factor: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown: number;
  recovery_factor: number;
  expectancy: number;
  win_rate: number;
  avg_trade_return: number;
  trades: number;
};

type EquityPoint = { time: string; value: number };
type Marker = { time: string; price: number; sl?: number | null; tp?: number | null };
type Chart = {
  time: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  overlays: Record<string, (number | null)[]>;
  markers: Record<string, Marker[]>;
  oscillators?: Record<string, (number | null)[]>;
  downsample?: number;
};

/** Times look like "2026-07-17 02:30:00+00:00" (UTC). */
const markerHour = (time: string) => Number(time.slice(11, 13));
const markerDate = (time: string) => time.slice(0, 10); // YYYY-MM-DD
const fmtDayLabel = (time: string) =>
  `${time.slice(8, 10)}-${time.slice(5, 7)}-${time.slice(2, 4)}`; // DD-MM-AA

type ParamValue = number | boolean | string;
type BacktestResponse = {
  fitness: number;
  metrics: Metrics;
  equity: EquityPoint[];
  trade_returns: number[];
  chart: Chart | null;
  params: Record<string, ParamValue>;
};

const OVERLAY_COLORS = ["#38bdf8", "#a78bfa", "#fbbf24", "#f472b6", "#22d3ee", "#a3e635"];

function drawdownSeries(equity: EquityPoint[]): number[] {
  let peak = -Infinity;
  return equity.map((point) => {
    peak = Math.max(peak, point.value);
    return peak > 0 ? (point.value / peak - 1) * 100 : 0;
  });
}

const pct = (value: number) => `${(value * 100).toFixed(2)}%`;
const num = (value: number) => value.toFixed(2);

const METRIC_VIEW: { key: keyof Metrics; label: string; fmt: (v: number) => string }[] = [
  { key: "total_return", label: "Total return", fmt: pct },
  { key: "cagr", label: "CAGR", fmt: pct },
  { key: "max_drawdown", label: "Max drawdown", fmt: pct },
  { key: "win_rate", label: "Win rate", fmt: pct },
  { key: "profit_factor", label: "Profit factor", fmt: num },
  { key: "sharpe", label: "Sharpe", fmt: num },
  { key: "sortino", label: "Sortino", fmt: num },
  { key: "calmar", label: "Calmar", fmt: num },
  { key: "recovery_factor", label: "Recovery", fmt: num },
  { key: "expectancy", label: "Expectancy", fmt: num },
  { key: "avg_trade_return", label: "Avg trade", fmt: pct },
  { key: "trades", label: "Trades", fmt: (v) => String(v) },
];

function defaultParams(strategy: StrategyInfo | undefined): Record<string, ParamValue> {
  if (!strategy) return {};
  return Object.fromEntries(strategy.parameters.map((p) => [p.name, p.default]));
}

function ParamField({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: ParamValue;
  onChange: (v: ParamValue) => void;
}) {
  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200";
  const hint =
    spec.kind === "int" || spec.kind === "float"
      ? `${spec.low ?? "−∞"} … ${spec.high ?? "∞"}`
      : spec.kind === "bool"
        ? "on / off"
        : (spec.choices ?? []).join(" · ");

  const doc = PARAM_DOCS[spec.name];

  return (
    <label className="flex flex-col gap-1">
      <span className="group relative flex items-center gap-1 font-mono text-[11px] text-slate-400">
        <span className={doc ? "cursor-help underline decoration-dotted decoration-slate-600 underline-offset-2" : ""}>
          {spec.name}
        </span>
        {doc && (
          <span className="pointer-events-none absolute bottom-full left-0 z-40 mb-1.5 hidden w-64 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-2.5 font-sans text-[11px] leading-relaxed text-slate-300 shadow-xl group-hover:block">
            {doc}
          </span>
        )}
      </span>
      {spec.kind === "bool" ? (
        <span
          className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1 text-sm transition ${
            value
              ? "border-emerald-600 bg-emerald-600/20 text-emerald-300"
              : "border-slate-700 bg-slate-800 text-slate-400"
          }`}
          onClick={() => onChange(!(value as boolean))}
        >
          <input
            type="checkbox"
            checked={value as boolean}
            onChange={(e) => onChange(e.target.checked)}
            onClick={(e) => e.stopPropagation()}
            className="h-3.5 w-3.5 accent-emerald-500"
          />
          {value ? "activado" : "desactivado"}
        </span>
      ) : spec.kind === "categorical" ? (
        <select
          className={inputClass}
          value={value as string}
          onChange={(e) => onChange(e.target.value)}
        >
          {(spec.choices ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="number"
          className={inputClass}
          value={value as number}
          min={spec.low ?? undefined}
          max={spec.high ?? undefined}
          step={spec.kind === "int" ? 1 : (spec.step ?? "any")}
          onChange={(e) => onChange(spec.kind === "int" ? Math.round(+e.target.value) : +e.target.value)}
        />
      )}
      <span className="text-[10px] text-slate-600">{hint}</span>
    </label>
  );
}

export default function BacktestPanel() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [dataset, setDataset] = useState("");
  // Strategy checklist: ids the user has excluded from the backtest dropdown.
  const [excluded, setExcluded] = useState<string[]>([]);
  const [showPicker, setShowPicker] = useState(false);
  const [params, setParams] = useState<Record<string, ParamValue>>({});
  const [showParams, setShowParams] = useState(true);
  const [initialCash, setInitialCash] = useState(10000);
  const [months, setMonths] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  // Trained "win" classification models available as meta-labeling filters.
  const [models, setModels] = useState<ModelOption[]>([]);
  const [mlModelId, setMlModelId] = useState("");
  // Completed optimization studies whose best params can be loaded here.
  const [studies, setStudies] = useState<StudyOption[]>([]);
  const [loadedStudy, setLoadedStudy] = useState<string | null>(null);
  // Best params to apply *after* a strategy switch settles (the switch resets
  // params to defaults, so loading a study defers the values through this ref).
  const pendingParams = useRef<Record<string, ParamValue> | null>(null);
  // Chart-level filters (UTC): zoom the chart to a date range and/or hour band.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [hourFrom, setHourFrom] = useState(0);
  const [hourTo, setHourTo] = useState(23);

  const strategy = useMemo(
    () => strategies.find((s) => s.strategy_id === strategyId),
    [strategies, strategyId],
  );

  const selectedModel = useMemo(
    () => models.find((m) => m.id === mlModelId),
    [models, mlModelId],
  );

  // The ML filter is only coherent when the strategy's SL/TP match what the
  // model was trained to predict. Flag the mismatch when the filter is active.
  const mlMismatch = useMemo(() => {
    if (!selectedModel || !params.use_ml_filter) return null;
    const stratSl = Number(params.sl_atr);
    const stratTp = Number(params.tp_atr);
    const mSl = modelSl(selectedModel);
    const mTp = modelTp(selectedModel);
    const off = (a: number, b: number) => Math.abs(a - b) > 1e-6;
    if (off(stratSl, mSl) || off(stratTp, mTp)) {
      return { stratSl, stratTp, mSl, mTp };
    }
    return null;
  }, [selectedModel, params]);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("ql.backtest.excluded") ?? "[]");
      if (Array.isArray(saved)) setExcluded(saved.filter((x) => typeof x === "string"));
    } catch {
      // corrupted storage: fall back to everything enabled
    }
    apiFetch("/strategies", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StrategyInfo[]) => {
        setStrategies(list);
        if (list.length > 0) setStrategyId(list[0].strategy_id);
      })
      .catch(() => setStrategies([]));
    apiFetch("/datasets", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: DatasetOption[]) => {
        const ready = list.filter((d) => d.status === "ready");
        setDatasets(ready);
        if (ready.length > 0) setDataset(`${ready[0].symbol}|${ready[0].timeframe}`);
      })
      .catch(() => setDatasets([]));
    apiFetch("/ml/models", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: ModelOption[]) =>
        setModels(list.filter((m) => m.status === "completed" && m.target === "win")),
      )
      .catch(() => setModels([]));
    apiFetch("/optimizations", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((list: StudyOption[]) =>
        setStudies(list.filter((s) => s.status === "completed" && s.best_params)),
      )
      .catch(() => setStudies([]));
  }, []);

  // Reset the editable parameters to the strategy's declared defaults on switch —
  // unless a study load is pending, in which case apply its best params on top.
  useEffect(() => {
    const base = defaultParams(strategy);
    if (pendingParams.current) {
      setParams({ ...base, ...pendingParams.current });
      pendingParams.current = null;
    } else {
      setParams(base);
    }
  }, [strategy]);

  // Load an optimization's winning parameters into the editor (and match its
  // strategy + dataset). Unknown keys are dropped so the backtest never 422s.
  const loadStudy = useCallback(
    (study: StudyOption) => {
      const strat = strategies.find((s) => s.strategy_id === study.strategy_id);
      if (!strat || !study.best_params) return;
      const valid = new Set(strat.parameters.map((p) => p.name));
      const best = Object.fromEntries(
        Object.entries(study.best_params).filter(([k]) => valid.has(k)),
      ) as Record<string, ParamValue>;
      const ds = `${study.symbol}|${study.timeframe}`;
      if (datasets.some((d) => `${d.symbol}|${d.timeframe}` === ds)) setDataset(ds);
      if (study.strategy_id === strategyId) {
        setParams({ ...defaultParams(strat), ...best }); // strategy unchanged: apply now
      } else {
        pendingParams.current = best; // strategy switch resets, then applies these
        setStrategyId(study.strategy_id);
      }
      setLoadedStudy(study.id);
    },
    [strategies, datasets, strategyId],
  );

  const visibleStrategies = useMemo(
    () => strategies.filter((s) => !excluded.includes(s.strategy_id)),
    [strategies, excluded],
  );

  // If the selected strategy gets unchecked, fall back to the first visible one.
  useEffect(() => {
    if (strategyId && excluded.includes(strategyId)) {
      setStrategyId(visibleStrategies[0]?.strategy_id ?? "");
    }
  }, [excluded, strategyId, visibleStrategies]);

  const toggleExcluded = useCallback((id: string) => {
    setExcluded((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      window.localStorage.setItem("ql.backtest.excluded", JSON.stringify(next));
      return next;
    });
  }, []);

  const setParam = useCallback((name: string, value: ParamValue) => {
    setParams((prev) => ({ ...prev, [name]: value }));
    setLoadedStudy(null); // a manual edit means the params no longer match a study
  }, []);

  const runBacktest = async () => {
    if (!strategyId || !dataset) return;
    const [symbol, timeframe] = dataset.split("|");
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiFetch("/backtests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          symbol,
          timeframe,
          params,
          chart_bars: 400,
          initial_cash: initialCash > 0 ? initialCash : 10000,
          months: months ? Number(months) : null,
          ml_model_id: mlModelId || null,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Backtest failed");
      } else {
        setResult(body);
      }
    } catch {
      setError("Backend unreachable");
    } finally {
      setRunning(false);
    }
  };

  const selectClass =
    "rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200";

  // A bar/marker passes when its UTC date and hour fall inside the filters.
  const markerVisible = useCallback(
    (time: string) => {
      const date = markerDate(time); // ISO dates compare correctly as strings
      if (dateFrom && date < dateFrom) return false;
      if (dateTo && date > dateTo) return false;
      const hour = markerHour(time);
      return hourFrom <= hourTo
        ? hour >= hourFrom && hour <= hourTo
        : hour >= hourFrom || hour <= hourTo; // range wrapping midnight
    },
    [dateFrom, dateTo, hourFrom, hourTo],
  );

  // View of the chart data restricted to the active day/hour filter: only the
  // matching bars remain (a "zoom" onto the selected window, bars compressed
  // side by side). With no filter, it is the full chart unchanged.
  const chartView = useMemo(() => {
    const c = result?.chart;
    if (!c) return null;
    const filterActive = dateFrom !== "" || dateTo !== "" || hourFrom !== 0 || hourTo !== 23;
    if (!filterActive) return c;
    const keep = c.time.map((t) => markerVisible(t));
    const sel = <T,>(arr: T[]): T[] => arr.filter((_, i) => keep[i]);
    return {
      time: sel(c.time),
      open: sel(c.open),
      high: sel(c.high),
      low: sel(c.low),
      close: sel(c.close),
      overlays: Object.fromEntries(Object.entries(c.overlays).map(([k, v]) => [k, sel(v)])),
      oscillators: c.oscillators
        ? Object.fromEntries(Object.entries(c.oscillators).map(([k, v]) => [k, sel(v)]))
        : undefined,
      markers: c.markers,
    };
  }, [result, markerVisible, dateFrom, dateTo, hourFrom, hourTo]);

  // ~8 evenly spaced x-axis ticks labeled DD-MM-AA (the axis is categorical,
  // so tick labels must be provided explicitly).
  const dateTicks = useMemo(() => {
    const times = chartView?.time ?? [];
    if (times.length === 0) return {};
    const count = Math.min(8, times.length);
    const idxs = Array.from({ length: count }, (_, k) =>
      Math.floor((k * (times.length - 1)) / Math.max(1, count - 1)),
    );
    const tickvals = [...new Set(idxs)].map((i) => times[i]);
    return { tickmode: "array", tickvals, ticktext: tickvals.map(fmtDayLabel) };
  }, [chartView]);

  const filteredEntryCount = useMemo(() => {
    if (!result?.chart) return { shown: 0, total: 0 };
    const entries = [
      ...(result.chart.markers.long_entry ?? []),
      ...(result.chart.markers.short_entry ?? []),
    ];
    return { shown: entries.filter((m) => markerVisible(m.time)).length, total: entries.length };
  }, [result, markerVisible]);

  const priceTraces = useMemo(() => {
    if (!result?.chart || !chartView) return [];
    const c = result.chart; // markers: always the full set, filtered below
    const traces: unknown[] = [
      {
        type: "candlestick",
        x: chartView.time,
        open: chartView.open,
        high: chartView.high,
        low: chartView.low,
        close: chartView.close,
        name: "price",
        increasing: { line: { color: "#34d399", width: 1 } },
        decreasing: { line: { color: "#fb7185", width: 1 } },
        showlegend: false,
      },
    ];
    Object.entries(chartView.overlays).forEach(([name, values], i) => {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: chartView.time,
        y: values,
        name,
        connectgaps: false,
        line: { color: OVERLAY_COLORS[i % OVERLAY_COLORS.length], width: 1.3 },
      });
    });
    const markerTrace = (
      key: string,
      name: string,
      symbol: string,
      color: string,
      yshift: number,
    ) => {
      const pts = (c.markers[key] ?? []).filter((p) => markerVisible(p.time));
      if (pts.length === 0) return null;
      return {
        type: "scatter",
        mode: "markers",
        x: pts.map((p) => p.time),
        y: pts.map((p) => p.price * (1 + yshift)),
        name,
        marker: { symbol, color, size: 9, line: { color: "#0b1120", width: 1 } },
        hovertemplate: `${name} @ %{y:.5f}<extra></extra>`,
      };
    };
    const longEntry = markerTrace("long_entry", "long entry", "triangle-up", "#34d399", -0.001);
    const shortEntry = markerTrace("short_entry", "short entry", "triangle-down", "#fb7185", 0.001);
    const exits = [...(c.markers.long_exit ?? []), ...(c.markers.short_exit ?? [])].filter((p) =>
      markerVisible(p.time),
    );
    const exitTrace =
      exits.length > 0
        ? {
            type: "scatter",
            mode: "markers",
            x: exits.map((p) => p.time),
            y: exits.map((p) => p.price),
            name: "exit",
            marker: { symbol: "x", color: "#94a3b8", size: 6 },
            hovertemplate: "exit @ %{y:.5f}<extra></extra>",
          }
        : null;

    // SL/TP levels the order plan placed at each (visible) entry.
    const entriesWithLevels = [
      ...(c.markers.long_entry ?? []),
      ...(c.markers.short_entry ?? []),
    ].filter((p) => markerVisible(p.time));
    const levelTrace = (key: "sl" | "tp", name: string, color: string) => {
      const pts = entriesWithLevels.filter((p) => p[key] != null);
      if (pts.length === 0) return null;
      return {
        type: "scatter",
        mode: "markers",
        x: pts.map((p) => p.time),
        y: pts.map((p) => p[key]),
        name,
        marker: { symbol: "line-ew-open", color, size: 11, line: { color, width: 2 } },
        hovertemplate: `${name} @ %{y:.5f}<extra></extra>`,
      };
    };
    const slTrace = levelTrace("sl", "SL", "#f43f5e");
    const tpTrace = levelTrace("tp", "TP", "#10b981");

    return [...traces, longEntry, shortEntry, exitTrace, slTrace, tpTrace].filter(Boolean);
  }, [result, chartView, markerVisible]);

  return (
    <section className="mt-10">
      <h2 className="mb-4 text-xl font-semibold">Quick backtest</h2>
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <select
            className={selectClass}
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
          >
            {visibleStrategies.map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowPicker((v) => !v)}
            title="Elegir qué estrategias están disponibles en el backtest"
            className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-400 transition hover:text-slate-200"
          >
            ☑ {visibleStrategies.length}/{strategies.length}
          </button>
          <select className={selectClass} value={dataset} onChange={(e) => setDataset(e.target.value)}>
            {datasets.length === 0 ? (
              <option value="">No datasets ready</option>
            ) : (
              datasets.map((d) => (
                <option key={`${d.symbol}|${d.timeframe}`} value={`${d.symbol}|${d.timeframe}`}>
                  {d.symbol} · {d.timeframe}
                </option>
              ))
            )}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            Capital
            <span className="flex items-center rounded-lg border border-slate-700 bg-slate-800 pl-2 text-sm text-slate-200">
              <span className="text-slate-500">$</span>
              <input
                type="number"
                min={1}
                step={1000}
                value={initialCash}
                onChange={(e) => setInitialCash(Number(e.target.value))}
                className="w-24 bg-transparent px-1 py-1.5 text-sm outline-none"
              />
            </span>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            Period
            <select
              className={selectClass}
              value={months}
              onChange={(e) => setMonths(e.target.value)}
            >
              <option value="">All history</option>
              <option value="1">Last 1 month</option>
              <option value="3">Last 3 months</option>
              <option value="6">Last 6 months</option>
              <option value="12">Last 12 months</option>
              <option value="24">Last 24 months</option>
              <option value="36">Last 36 months</option>
            </select>
          </label>
          <label
            className="flex items-center gap-1.5 text-xs text-slate-400"
            title="Filtro de meta-labeling: solo entra donde el modelo predice alta probabilidad de ganar. Requiere activar use_ml_filter y ajustar ml_threshold en los parámetros."
          >
            Filtro ML
            <select
              className={selectClass}
              value={mlModelId}
              onChange={(e) => setMlModelId(e.target.value)}
            >
              <option value="">Ninguno</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  win · {m.symbol} {m.timeframe} · {m.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={runBacktest}
            disabled={running || !strategyId || !dataset}
            className="rounded-lg border border-emerald-700 bg-emerald-600/20 px-4 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {running ? "Running…" : "Run backtest"}
          </button>
          {result && (
            <span className="ml-auto flex items-center gap-3 text-sm text-slate-400">
              {dataset && (
                <SendToAutoTrader
                  strategyId={strategyId}
                  symbol={dataset.split("|")[0]}
                  timeframe={dataset.split("|")[1]}
                  params={result.params}
                  mlModelId={mlModelId || null}
                />
              )}
              <span>
                Fitness:{" "}
                <span
                  className={`font-semibold ${result.fitness >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {result.fitness.toFixed(4)}
                </span>
              </span>
            </span>
          )}
        </div>

        {showPicker && (
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="mb-2 flex items-center gap-3">
              <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                Estrategias disponibles en el backtest — desmarca las que no quieras usar
              </p>
              <button
                onClick={() => {
                  setExcluded([]);
                  window.localStorage.setItem("ql.backtest.excluded", "[]");
                }}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-slate-800"
              >
                Todas
              </button>
              <button
                onClick={() => {
                  const all = strategies.map((s) => s.strategy_id);
                  setExcluded(all);
                  window.localStorage.setItem("ql.backtest.excluded", JSON.stringify(all));
                }}
                className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-slate-800"
              >
                Ninguna
              </button>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3 lg:grid-cols-4">
              {strategies.map((s) => {
                const active = !excluded.includes(s.strategy_id);
                return (
                  <label
                    key={s.strategy_id}
                    className={`flex cursor-pointer items-center gap-2 text-xs ${
                      active ? "text-slate-200" : "text-slate-500"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() => toggleExcluded(s.strategy_id)}
                      className="h-3.5 w-3.5 accent-[#2b6ef2]"
                    />
                    {s.name}
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {strategy && (
          <p className="mt-3 text-xs text-slate-500">{strategy.description}</p>
        )}

        {studies.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>Cargar parámetros de una optimización:</span>
            <select
              className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
              value=""
              onChange={(e) => {
                const s = studies.find((x) => x.id === e.target.value);
                if (s) loadStudy(s);
              }}
            >
              <option value="">— elige un estudio —</option>
              {studies.map((s) => {
                const name =
                  strategies.find((st) => st.strategy_id === s.strategy_id)?.name ?? s.strategy_id;
                return (
                  <option key={s.id} value={s.id}>
                    {name} · {s.symbol} {s.timeframe} · score{" "}
                    {s.best_score != null ? s.best_score.toFixed(3) : "—"}
                  </option>
                );
              })}
            </select>
            {loadedStudy && (
              <span className="text-emerald-400">✓ mejores parámetros cargados</span>
            )}
          </div>
        )}

        {mlMismatch && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            <span>
              ⚠️ El modelo se entrenó con <b>SL {mlMismatch.mSl}·ATR / TP {mlMismatch.mTp}·ATR</b>,
              pero la estrategia usa <b>SL {mlMismatch.stratSl}·ATR / TP {mlMismatch.stratTp}·ATR</b>.
              La P(ganar) mide salidas distintas a las tuyas — el filtro pierde coherencia.
            </span>
            <button
              onClick={() => {
                setParam("sl_atr", mlMismatch.mSl);
                setParam("tp_atr", mlMismatch.mTp);
              }}
              className="ml-auto whitespace-nowrap rounded border border-amber-500/40 bg-amber-500/15 px-2 py-1 font-medium text-amber-200 hover:bg-amber-500/25"
            >
              Alinear SL/TP al modelo
            </button>
          </div>
        )}

        {/* Parameter editor */}
        {strategy && (
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40">
            <button
              onClick={() => setShowParams((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-400 hover:text-slate-200"
            >
              <span>Parameters &amp; filters · {strategy.parameters.length}</span>
              <span className="flex items-center gap-3">
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    setParams(defaultParams(strategy));
                  }}
                  className="rounded border border-slate-700 px-2 py-0.5 text-[10px] normal-case text-slate-400 hover:bg-slate-800"
                >
                  Reset defaults
                </span>
                <span className="text-slate-600">{showParams ? "▲" : "▼"}</span>
              </span>
            </button>
            {showParams && (
              <div className="border-t border-slate-800 p-4">
                {PARAM_GROUPS.map(({ key, label }) => {
                  const specs = strategy.parameters.filter((p) => (p.group ?? "strategy") === key);
                  if (specs.length === 0) return null;
                  return (
                    <div key={key} className="mb-4 last:mb-0">
                      <p
                        className={`mb-2 font-mono text-[10px] uppercase tracking-wider ${
                          key === "filter" ? "text-sky-400" : "text-slate-500"
                        }`}
                      >
                        {label}
                      </p>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
                        {specs.map((spec) => (
                          <ParamField
                            key={spec.name}
                            spec={spec}
                            value={params[spec.name] ?? spec.default}
                            onChange={(v) => setParam(spec.name, v)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
        {datasets.length === 0 && !error && (
          <p className="mt-3 text-xs text-slate-500">Sync a dataset first to run a backtest.</p>
        )}

        {result && (
          <>
            {/* Price + strategy logic (last 400 bars) */}
            {result.chart && result.chart.time.length > 0 && (
              <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <div className="flex flex-wrap items-center gap-3 px-2 pt-1">
                  <p className="text-xs text-slate-500">
                    Price &amp; entry logic — {chartView?.time.length ?? 0} bars (▲ long / ▼ short,
                    ✕ exits, ─ niveles SL/TP)
                    {(result.chart.downsample ?? 1) > 1 && (
                      <span className="ml-1 text-slate-600">
                        · rango completo, cada barra ≈ {result.chart.downsample} velas
                      </span>
                    )}
                  </p>
                  <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <label className="flex items-center gap-1">
                      Fecha
                      <input
                        type="date"
                        className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200 [color-scheme:dark]"
                        value={dateFrom}
                        min={markerDate(result.chart.time[0])}
                        max={markerDate(result.chart.time[result.chart.time.length - 1])}
                        onChange={(e) => setDateFrom(e.target.value)}
                      />
                      –
                      <input
                        type="date"
                        className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200 [color-scheme:dark]"
                        value={dateTo}
                        min={markerDate(result.chart.time[0])}
                        max={markerDate(result.chart.time[result.chart.time.length - 1])}
                        onChange={(e) => setDateTo(e.target.value)}
                      />
                    </label>
                    <label className="flex items-center gap-1">
                      Hora (UTC)
                      <select
                        className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200"
                        value={hourFrom}
                        onChange={(e) => setHourFrom(Number(e.target.value))}
                      >
                        {Array.from({ length: 24 }, (_, h) => (
                          <option key={h} value={h}>
                            {String(h).padStart(2, "0")}
                          </option>
                        ))}
                      </select>
                      –
                      <select
                        className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200"
                        value={hourTo}
                        onChange={(e) => setHourTo(Number(e.target.value))}
                      >
                        {Array.from({ length: 24 }, (_, h) => (
                          <option key={h} value={h}>
                            {String(h).padStart(2, "0")}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] ${
                        filteredEntryCount.shown < filteredEntryCount.total
                          ? "border-sky-500/30 bg-sky-500/10 text-sky-400"
                          : "border-slate-700 text-slate-500"
                      }`}
                    >
                      {filteredEntryCount.shown}/{filteredEntryCount.total} entradas
                    </span>
                    {(dateFrom !== "" || dateTo !== "" || hourFrom !== 0 || hourTo !== 23) && (
                      <button
                        onClick={() => {
                          setDateFrom("");
                          setDateTo("");
                          setHourFrom(0);
                          setHourTo(23);
                        }}
                        className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-slate-800"
                      >
                        Limpiar
                      </button>
                    )}
                  </div>
                </div>
                {chartView && chartView.time.length === 0 ? (
                  <p className="px-2 py-6 text-center text-xs text-slate-500">
                    Ninguna vela cae en ese filtro de día/hora — ajusta la franja o pulsa Limpiar.
                  </p>
                ) : (
                  <>
                    <PlotlyChart
                      data={priceTraces}
                      layout={{
                        xaxis: { type: "category", rangeslider: { visible: false }, ...dateTicks },
                        showlegend: true,
                        legend: { orientation: "h", y: 1.04, x: 0, font: { size: 10 } },
                        margin: { t: 30, r: 12, b: 30, l: 56 },
                      }}
                      height={420}
                    />
                    {chartView?.oscillators &&
                      Object.entries(chartView.oscillators).map(([name, values]) => (
                        <div key={name} className="mt-1 border-t border-slate-800/60 pt-1">
                          <p className="px-2 text-[10px] text-slate-500">
                            {name} — sobrecompra &gt;70 · sobreventa &lt;30
                          </p>
                          <PlotlyChart
                            data={[
                              {
                                type: "scatter",
                                mode: "lines",
                                x: chartView.time,
                                y: values,
                                name,
                                line: { color: "#a78bfa", width: 1.3 },
                                hovertemplate: "%{x}<br>%{y:.1f}<extra></extra>",
                              },
                              {
                                type: "scatter",
                                mode: "lines",
                                x: chartView.time,
                                y: chartView.time.map(() => 70),
                                line: { color: "rgba(251,113,133,0.5)", width: 1, dash: "dot" },
                                hoverinfo: "skip",
                                showlegend: false,
                              },
                              {
                                type: "scatter",
                                mode: "lines",
                                x: chartView.time,
                                y: chartView.time.map(() => 30),
                                line: { color: "rgba(52,211,153,0.5)", width: 1, dash: "dot" },
                                hoverinfo: "skip",
                                showlegend: false,
                              },
                            ]}
                            layout={{
                              xaxis: { type: "category", ...dateTicks },
                              yaxis: { range: [0, 100] },
                              showlegend: false,
                              margin: { t: 6, r: 12, b: 24, l: 56 },
                            }}
                            height={150}
                          />
                        </div>
                      ))}
                  </>
                )}
              </div>
            )}

            {/* Metrics */}
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {METRIC_VIEW.map(({ key, label, fmt }) => (
                <div key={key} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-sm font-semibold tabular-nums">{fmt(result.metrics[key])}</p>
                </div>
              ))}
            </div>

            {/* Equity + drawdown */}
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">
                  Equity curve
                  {result.equity.length > 0 && (
                    <span className="ml-1 tabular-nums">
                      · ${Math.round(result.equity[0].value).toLocaleString()} →{" "}
                      <span
                        className={
                          result.equity[result.equity.length - 1].value >= result.equity[0].value
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }
                      >
                        ${Math.round(result.equity[result.equity.length - 1].value).toLocaleString()}
                      </span>
                    </span>
                  )}
                </p>
                <PlotlyChart
                  data={[
                    {
                      x: result.equity.map((p) => p.time),
                      y: result.equity.map((p) => p.value),
                      type: "scatter",
                      mode: "lines",
                      line: { color: "#34d399", width: 1.5 },
                      hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
                    },
                  ]}
                  height={240}
                />
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">Drawdown</p>
                <PlotlyChart
                  data={[
                    {
                      x: result.equity.map((p) => p.time),
                      y: drawdownSeries(result.equity),
                      type: "scatter",
                      mode: "lines",
                      fill: "tozeroy",
                      line: { color: "#fb7185", width: 1 },
                      fillcolor: "rgba(251,113,133,0.15)",
                      hovertemplate: "%{x}<br>%{y:.2f}%<extra></extra>",
                    },
                  ]}
                  layout={{ yaxis: { ticksuffix: "%" } }}
                  height={240}
                />
              </div>
            </div>

            {/* Trade distribution */}
            {result.trade_returns.length > 0 && (
              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                <p className="px-2 pt-1 text-xs text-slate-500">
                  Trade return distribution ({result.trade_returns.length} trades)
                </p>
                <PlotlyChart
                  data={[
                    {
                      x: result.trade_returns.map((r) => r * 100),
                      type: "histogram",
                      nbinsx: 60,
                      marker: { color: "#38bdf8", opacity: 0.85 },
                      hovertemplate: "%{x:.2f}%: %{y} trades<extra></extra>",
                    },
                  ]}
                  layout={{ xaxis: { ticksuffix: "%" }, bargap: 0.05 }}
                  height={220}
                />
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
