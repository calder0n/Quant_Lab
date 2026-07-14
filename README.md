# QuantLab

Laboratorio de investigación cuantitativa: descubrimiento masivo de estrategias mediante
backtesting, optimización y validación robusta. Ejecución 100% local sobre Docker.

> **Estado:** Fase 6 — Machine Learning (XGBoost/LightGBM/CatBoost/PyTorch) + RL (Gymnasium + SB3).

## Stack

FastAPI · Next.js + Tailwind · PostgreSQL · Redis · SQLAlchemy 2 (async) · Alembic ·
Docker Compose. En fases posteriores: vectorbt, Backtesting.py, Optuna, XGBoost/LightGBM/
CatBoost, PyTorch, Stable-Baselines3, OANDA.

## Arranque rápido

```bash
cp .env.example .env   # opcional en Fase 1: los defaults funcionan
make up
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8080/docs
- Health: http://localhost:8080/api/v1/health

(Puertos en el host: API 8080→8000 y PostgreSQL 5433→5432, para no chocar con
servicios locales ya existentes.)

## Calidad

```bash
make test              # pytest + cobertura mínima 90%
make test-integration  # incluye tests contra Postgres/Redis reales
make lint              # ruff + black --check
make typecheck         # mypy --strict
make check             # todo lo anterior
```

## Descarga de datos históricos

1. Crea un token en OANDA (una cuenta *practice* gratuita sirve).
2. Configúralo en el portal: **Broker settings** → API token + Account ID + entorno →
   *Save* → *Test connection*. Las credenciales se guardan en tu PostgreSQL local,
   el token nunca se vuelve a mostrar (solo enmascarado) y tienen prioridad sobre
   las variables `QL_OANDA_*` del `.env` (que siguen funcionando como alternativa).
3. Ajusta `QL_HISTORY_START` si quieres más histórico (por defecto `2020-01-01`).
4. Pulsa **Sync history** en el dashboard
   (o `curl -X POST localhost:8080/api/v1/datasets/sync -H 'Content-Type: application/json' -d '{}'`).

La descarga es **idempotente**: la cobertura real vive en los Parquet
(`/data/candles/{SYMBOL}/{TF}.parquet`, volumen `marketdata`) y solo se piden a la API
los rangos que faltan. Repetir el sync solo trae velas nuevas.

## Estrategias y backtesting

- 15 estrategias en `backend/src/quantlab/strategies/plugins/` (una por archivo,
  auto-descubiertas). Añadir una estrategia = crear un archivo que implemente
  `load / generate_signals / generate_orders / fitness / metadata`.
- Cada plugin declara sus parámetros optimizables (`ParameterSpec`) y hereda los
  de riesgo comunes: `sl_atr`, `tp_atr`, `use_trailing`, filtro horario y de spread.
- Motor: vectorbt tras el puerto `BacktestEngine` (señales desplazadas 1 barra,
  costes: comisión + slippage + medio spread real por lado).
- Prueba sin broker: `make seed-demo` crea un dataset sintético EURUSD/H1
  (elimínalo con `make clean-demo` antes de sincronizar datos reales).

## Optimización masiva

- Lanza estudios desde el panel **Optimization** (o `POST /api/v1/optimizations`):
  estrategia × dataset × nº de trials × optimizador.
- Optimizadores tras el puerto `Optimizer`: `optuna` (TPE/bayesiano) y `random`
  (baseline). Añadir GA/Nevergrad = un adaptador más con la misma interfaz.
- Función objetivo configurable por estudio: pesos sobre las 12 métricas
  normalizadas + restricciones (`min_trades`, `max_drawdown_limit`).
- Los estudios corren en **workers** (contenedor `worker`, cola arq sobre Redis).
  Escala con: `docker compose up -d --scale worker=4`. Estado en `GET /api/v1/workers`.
- Cada trial se persiste al completarse: progreso y ranking en vivo en el dashboard.

## Validación robusta

Nunca aceptes una estrategia solo porque ganó el backtest. Panel **Validation**
(o `POST /api/v1/validations`), tres métodos que corren en los workers:

- **Walk-Forward**: optimiza en cada ventana in-sample y evalúa los mejores
  parámetros en la ventana out-of-sample siguiente (rodante o anclado).
  La *eficiencia WF* (score OOS/IS) cerca de 1 indica robustez; cerca de 0,
  curve-fitting. Config: `n_folds`, `train_ratio`, `n_trials`, `optimizer`,
  `objective`, `anchored`, `seed`.
- **Monte Carlo**: remuestrea los retornos por trade (`resample` bootstrap o
  `shuffle` permutación) y reporta percentiles de retorno final y drawdown,
  P(pérdida) y P(ruina, DD>50%). Config: `n_runs`, `method`, `seed`.
- **Stress**: re-ejecuta bajo escenarios hostiles — spread ×2/×3, comisión,
  slippage, retraso aleatorio de señales de 1-3 barras y el combo de todo —
  y mide la degradación frente al baseline. Config: `scenarios` (opcional).

## Machine Learning y RL

Panel **Machine Learning** (o `POST /api/v1/ml/models`); entrena en los workers:

- **ML supervisado** (`kind: ml`): features causales + etiquetado triple-barrera
  (SL/TP a múltiplos de ATR, horizonte de N barras). Objetivos: `win` (P de TP
  primero), `sl_hit`, `tp_hit`, `expected_move` (regresión). Algoritmos:
  `xgboost`, `lightgbm`, `catboost`, `torch_mlp`. Split cronológico 70/15/15,
  métricas sobre el test final (AUC vs base rate / R²), importancia de features,
  artefacto en `/data/models/`.
- **RL** (`kind: rl`, algoritmo `ppo`): entorno Gymnasium con estados =
  features + posición, acciones = comprar/vender/cerrar/esperar, reward =
  retorno de la posición − costes. Entrena en el 80% inicial y evalúa la
  política determinista en el 20% final (held-out).

## Arquitectura (backend)

```
src/quantlab/
├── config.py          # Settings tipadas (pydantic-settings, prefijo QL_)
├── container.py       # Composition root (DI): engine, sesiones, redis, event bus
├── domain/            # Conceptos de negocio puros (eventos de dominio)
├── application/       # Casos de uso y puertos (EventBus)
├── infrastructure/    # Adaptadores: db (SQLAlchemy), cache (Redis)
└── interfaces/api/    # FastAPI (app factory, deps, rutas)
```

Reglas: sin estado global, dependencias siempre inyectadas desde el `Container`,
los módulos se comunican por eventos de dominio a través del `EventBus`.

## Hoja de ruta

| Fase | Contenido |
|------|-----------|
| 1 ✅ | Fundación: Docker, Clean Architecture, DI, Event Bus, health checks |
| 2 ✅ | Datos: adaptador OANDA, descarga histórica idempotente → Parquet + catálogo en PostgreSQL |
| 3 ✅ | Estrategias (plugins auto-descubiertos) + motor de backtesting |
| 4 ✅ | Optimización masiva (Optuna/GA/Nevergrad/Bayesian) con función objetivo configurable |
| 5 ✅ | Validación: Walk-Forward, Monte Carlo, stress testing, costes realistas |
| 6 ✅ | ML (clasificadores/regresores) y RL (Gymnasium + SB3) |
| 7 | Dashboard completo: heatmaps, equity, drawdown, ranking, logs |
| 8 | Administración (auth, roles, API keys) y ejecución paper/live vía OANDA |
