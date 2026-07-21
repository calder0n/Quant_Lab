# QuantLab — Guía de uso

Guía práctica para operar el laboratorio de principio a fin. Todo corre en Docker;
el dashboard es http://localhost:3000 y la API http://localhost:8080/docs (Swagger).

---

## 1. Arranque y acceso

```bash
make up          # levanta postgres, redis, api, worker y frontend
make ps          # estado de los contenedores
make logs        # logs en vivo de todos los servicios
make down        # apaga todo (los datos persisten en volúmenes)
```

**Primer arranque:**
1. Copia la configuración: `cp .env.example .env` y define un `QL_SECRET_KEY` propio
   (firma las sesiones y cifra el token del broker — no lo cambies después sin
   re-introducir el token de OANDA).
2. Abre http://localhost:3000 → te pedirá **crear la cuenta administradora**
   (solo es posible mientras no exista ninguna).
3. Inicia sesión. Roles: `admin` (todo) y `viewer` (solo lectura, útil para
   compartir el dashboard sin riesgo).

> Desarrollo sin login: `QL_AUTH_ENABLED=false` en `.env` y `make up`.

## 2. Conectar OANDA y descargar el histórico

1. Crea un token en OANDA (cuenta **practice** gratuita: https://www.oanda.com →
   Manage API Access) y localiza tu Account ID.
2. En el panel **Broker settings**: pega token + Account ID + entorno `practice`
   → **Save** → **Test connection** (debe listar tus cuentas). El token se guarda
   cifrado y nunca se vuelve a mostrar.
3. En **Datasets** pulsa **Sync history**. Descarga los 8 mercados × 7
   temporalidades desde `QL_HISTORY_START` (defecto 2020). La primera vez tarda
   (~25M velas); es **idempotente**: repetir el sync solo trae velas nuevas, y si
   se interrumpe, retoma donde quedó. Los Parquet viven en el volumen `marketdata`.

## 3. Explorar: backtest rápido

Panel **Quick backtest**: elige estrategia + dataset → **Run backtest**.
Devuelve las 12 métricas, curva de equity, drawdown y distribución de trades.
Usa parámetros por defecto — sirve para tantear, no para concluir.

Las 15 estrategias están en **Strategies**; cada una declara sus parámetros
optimizables (añadir una estrategia = crear un archivo en
`backend/src/quantlab/strategies/plugins/` con el contrato
`load / generate_signals / generate_orders / fitness / metadata`).

## 4. Optimizar en masa

Panel **Optimization**:

- **Strategy × Dataset × Trials × Optimizer** (`optuna` = TPE bayesiano;
  `random` = baseline) → **Launch study**. Corre en los workers; el progreso y
  el mejor score se actualizan en vivo. Click en una fila → top-10 trials.
- Vía API puedes configurar la **función objetivo** por estudio:

```bash
curl -X POST localhost:8080/api/v1/optimizations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "strategy_id": "donchian", "symbol": "XAUUSD", "timeframe": "H4",
  "optimizer": "optuna", "n_trials": 500, "seed": 42,
  "objective": {
    "weights": {"sharpe": 0.3, "calmar": 0.2, "profit_factor": 0.2,
                 "max_drawdown": 0.2, "win_rate": 0.1},
    "min_trades": 50, "max_drawdown_limit": 0.25
  }}'
```

  Métricas disponibles como pesos: `profit_factor, sharpe, sortino, calmar,
  max_drawdown, recovery_factor, expectancy, cagr, win_rate, avg_trade, trades,
  total_return`. Las restricciones (`min_trades`, `max_drawdown_limit`) colapsan
  el score a −1 (el optimizador abandona esa región).
- Más potencia: `docker compose up -d --scale worker=4` (un estudio por worker).
- El panel **Results** agrega todo: heatmap mercado×timeframe del mejor score y
  ranking global de trials.

## 5. Validar (obligatorio antes de creer en nada)

Panel **Validation** — tres métodos, siempre sobre el candidato del ranking:

| Método | Qué responde | Config clave | Aprobado si… |
|---|---|---|---|
| **Walk-Forward** | ¿Los parámetros re-optimizados siguen ganando en datos no vistos? | `n_folds` (5), `train_ratio` (0.7), `n_trials` (30), `anchored` | eficiencia WF ≳ 0.5 y la mayoría de folds OOS > 0 |
| **Stress test** | ¿Sobrevive a spread ×2/×3, comisiones, slippage y fills retrasados? | `scenarios` opcional | retorno positivo en la mayoría de escenarios |
| **Monte Carlo** | ¿Qué rango de resultados es esperable? | `n_runs` (1000), `method` | p5 tolerable, P(ruina) ≈ 0 |

Para validar los **parámetros exactos** de un trial ganador, pásalos por API en
`params` (el panel usa defaults):

```bash
curl -X POST localhost:8080/api/v1/validations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "kind": "stress", "strategy_id": "atr_breakout",
  "symbol": "XAUUSD", "timeframe": "H4",
  "params": {"breakout_atr": 1.8, "sl_atr": 2.5, "tp_atr": 4.0}}'
```

**Regla de oro:** optimizar → walk-forward → stress → Monte Carlo. Si falla
cualquiera, descarta o re-diseña; no "ajustes hasta que pase".

## 6. Machine Learning y RL

Panel **Machine Learning**:

- **ML supervisado**: objetivo (`win`, `sl_hit`, `tp_hit` con etiquetado
  triple-barrera, o `expected_move` regresión) × algoritmo (`xgboost`,
  `lightgbm`, `catboost`, `torch_mlp`) × dataset. Reporta AUC vs base rate (o
  R²/MAE), importancia de features, y guarda el artefacto en `/data/models/`.
  Config por API: `horizon` (barras), `sl_atr`, `tp_atr`, `max_rows`,
  `n_estimators`…
- **RL**: PPO sobre el entorno Gymnasium (estados = indicadores/precio/volumen/
  volatilidad/hora/spread + posición; acciones = comprar/vender/cerrar/esperar).
  Entrena en el 80% y evalúa la política en el 20% final. Sube `timesteps`
  (config) a 200k+ para entrenamientos serios.

Interpretación honesta: AUC 0.55–0.65 ya es señal en FX; desconfía de valores
altos (fuga de datos). El RL con pocos timesteps es fontanería, no una política.

## 7. Trading (paper → live), bajo tu control

Panel **Trading** (solo admin):

1. Estado de cuenta y posiciones en vivo del broker.
2. **Kill switch**: todo nace apagado. *Enable trading* lo activa; con
   credenciales `live` exige teclear `TRADE-LIVE`.
3. **Evaluate & execute signal**: evalúa la estrategia sobre velas frescas del
   broker y ejecuta la señal de la última barra cerrada — entrada → orden de
   mercado con SL/TP del plan de la estrategia; salida/reversa → cierre.

Recomendaciones: opera **solo** estrategias que pasaron la validación completa;
usa `practice` durante semanas antes de considerar `live`; los índices
(NAS100/SPX500/US30) van en unidades pequeñas (1 unidad ≈ 1 contrato CFD).
Para ejecución periódica, agenda el endpoint con cron:
`*/60 * * * * curl -X POST .../trading/execute -H "X-API-Key: $KEY" -d '{...}'`.

## 8. Acceso programático (API keys)

```bash
# crear una key (una sola vez se muestra el valor)
curl -X POST localhost:8080/api/v1/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" -d '{"name": "scripts"}'
# usarla
curl localhost:8080/api/v1/results/ranking -H "X-API-Key: ql_..."
```

Swagger completo en http://localhost:8080/docs. Login por API:
`POST /api/v1/auth/login {"username","password"}` → `access_token`.

## 9. Operación y mantenimiento

```bash
make test          # suite completa (cobertura mínima 90%)
make check         # lint + typing + tests
make migrate       # aplicar migraciones tras actualizar código
make seed-demo     # dataset sintético para probar sin broker (clean-demo lo quita)
```

- **Logs**: panel Logs (API + workers) o `make logs`.
- **Workers caídos**: el chip "workers offline" en Optimization lo delata;
  `docker compose restart worker`. Tras cambiar código de backend:
  `docker compose build api && docker compose up -d api worker` (comparten la
  imagen `quantlab-backend`).
- **Backups**: los datos viven en los volúmenes `pgdata` (Postgres),
  `marketdata` (Parquet + modelos) y `redisdata`.
- **Actualizar velas**: pulsa Sync history cuando quieras; solo baja lo nuevo.

## 10. Solución de problemas

| Síntoma | Causa probable | Remedio |
|---|---|---|
| "OANDA credentials not configured" | Falta token/account | Broker settings → Save → Test |
| Estudio `failed: No local data` | Dataset sin sincronizar | Sync history y reintenta |
| Estudio eterno en `pending` | Worker apagado o sin el job | `docker compose restart worker` |
| 401 en todo | Sesión expirada (12h) | Vuelve a iniciar sesión |
| "token cannot be decrypted" | Cambiaste `QL_SECRET_KEY` | Re-introduce el token en Broker settings |
| Puertos ocupados | Otros servicios locales | API=8080, Postgres=5433 ya remapeados |
