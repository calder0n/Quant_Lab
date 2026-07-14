# QuantLab

Laboratorio de investigación cuantitativa: descubrimiento masivo de estrategias mediante
backtesting, optimización y validación robusta. Ejecución 100% local sobre Docker.

> **Estado:** Fase 2 — Capa de datos (OANDA, Parquet, catálogo de datasets).

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

1. Crea un token en OANDA (una cuenta *practice* gratuita sirve) y ponlo en `.env`:
   `QL_OANDA_API_TOKEN=...`
2. Ajusta `QL_HISTORY_START` (por defecto `2020-01-01`).
3. `docker compose up -d` y pulsa **Sync history** en el dashboard
   (o `curl -X POST localhost:8080/api/v1/datasets/sync -H 'Content-Type: application/json' -d '{}'`).

La descarga es **idempotente**: la cobertura real vive en los Parquet
(`/data/candles/{SYMBOL}/{TF}.parquet`, volumen `marketdata`) y solo se piden a la API
los rangos que faltan. Repetir el sync solo trae velas nuevas.

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
| 3 | Estrategias (plugins auto-descubiertos) + motor de backtesting |
| 4 | Optimización masiva (Optuna/GA/Nevergrad/Bayesian) con función objetivo configurable |
| 5 | Validación: Walk-Forward, Monte Carlo, stress testing, costes realistas |
| 6 | ML (clasificadores/regresores) y RL (Gymnasium + SB3) |
| 7 | Dashboard completo: heatmaps, equity, drawdown, ranking, logs |
| 8 | Administración (auth, roles, API keys) y ejecución paper/live vía OANDA |
