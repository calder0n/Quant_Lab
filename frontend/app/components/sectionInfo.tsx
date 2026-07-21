import InfoModal, { InfoH, InfoTerm } from "./InfoModal";

/** Per-menu help content: what the section is, how to use it and how to read
 *  what it shows. Rendered by the info button next to each section's content. */
export const SECTION_INFO: Record<string, { title: string; body: React.ReactNode }> = {
  overview: {
    title: "Resumen del sistema",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Vista de salud de la plataforma: muestra si el backend (API), la base de datos
          (PostgreSQL) y la cola/caché (Redis) están operativos. Se actualiza sola cada 5 segundos.
        </p>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="Punto verde">todo operativo; los backtests, optimizaciones y el auto-trader pueden funcionar.</InfoTerm>
        <InfoTerm term="Degradado">algún componente falla — mira su tarjeta para ver el detalle del error.</InfoTerm>
        <InfoTerm term="Backend inalcanzable">la API no responde; revisa que los contenedores estén corriendo (docker compose ps).</InfoTerm>
      </>
    ),
  },

  data: {
    title: "Datos (datasets)",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Gestión de los datos históricos de velas descargados del broker (OANDA). Todo backtest,
          optimización o validación corre sobre un dataset local — nunca descarga datos al vuelo.
        </p>
        <InfoH>Cómo se usa</InfoH>
        <p className="mb-3">
          Elige símbolo y timeframe y lanza una sincronización. El estado pasa a
          <em> syncing</em> y luego <em>ready</em> cuando está listo para usarse. Re-sincronizar un
          dataset existente solo trae las velas nuevas desde la última descarga.
        </p>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="Coverage">rango de fechas disponible localmente; los backtests solo pueden operar dentro de ese rango.</InfoTerm>
        <InfoTerm term="Candles">número de velas almacenadas. Más velas = backtests más significativos estadísticamente.</InfoTerm>
        <InfoTerm term="ready / syncing / error">listo para usar / descargando / falló (reintenta o revisa credenciales del broker).</InfoTerm>
      </>
    ),
  },

  strategies: {
    title: "Estrategias",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Catálogo de estrategias disponibles como plugins. Cada una declara sus parámetros
          optimizables (con rangos), más los parámetros de riesgo y filtros de entrada comunes a
          todas.
        </p>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="Categoría">familia de la lógica: trend/momentum (ema_cross, macd), breakout (donchian, opening_range), reversión (rsi, bollinger, mean_reversion) o conceptos SMC/ICT (order blocks, fair value gaps, liquidity sweeps).</InfoTerm>
        <InfoTerm term="Parámetros">los rangos indican el espacio que explora el optimizador; el default es el punto de partida del backtest rápido.</InfoTerm>
        <p className="mt-3 text-slate-400">
          Una estrategia no es buena o mala en abstracto: depende del símbolo, timeframe y régimen
          de mercado. Usa Backtest para explorarla y Validación para confiar en ella.
        </p>
      </>
    ),
  },

  backtest: {
    title: "Backtest rápido y resultados",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Simula una estrategia sobre datos históricos locales: evalúa sus señales vela a vela,
          aplica stop-loss/take-profit del plan de órdenes, costes (spread, comisión, slippage) y
          produce métricas, curva de equity y distribución de trades.
        </p>
        <InfoH>Cómo se usa</InfoH>
        <p className="mb-3">
          Elige estrategia + dataset, ajusta capital inicial y periodo, edita parámetros si quieres
          (pasa el cursor sobre cada nombre para ver qué hace) y pulsa <em>Run backtest</em>. Si el
          resultado te convence, <em>Send to auto-trader</em> lo registra para operarlo en vivo con
          esos mismos parámetros.
        </p>
        <InfoH>Cómo interpretar las métricas</InfoH>
        <InfoTerm term="Total return / CAGR">ganancia total del periodo y su equivalente anualizado.</InfoTerm>
        <InfoTerm term="Max drawdown">peor caída desde un máximo de equity. El número que define cuánto dolor soportas: &gt;25% es difícil de sostener psicológica y financieramente.</InfoTerm>
        <InfoTerm term="Win rate">% de trades ganadores. Por sí solo no dice nada — un 35% con ganadores grandes puede ser excelente (estrategias de tendencia) y un 80% con perdedores enormes puede quebrar la cuenta.</InfoTerm>
        <InfoTerm term="Profit factor">ganancias brutas ÷ pérdidas brutas. &lt;1 pierde dinero; 1.15–1.5 es sólido en intradía; &gt;3 con pocos trades suele ser sobreajuste.</InfoTerm>
        <InfoTerm term="Sharpe / Sortino">retorno por unidad de riesgo (Sortino solo penaliza volatilidad a la baja). &gt;1 bueno, &gt;2 muy bueno.</InfoTerm>
        <InfoTerm term="Calmar / Recovery">retorno relativo al drawdown — cuánto pagas en caídas por lo que ganas.</InfoTerm>
        <InfoTerm term="Expectancy / Avg trade">ganancia media esperada por trade. Debe superar con margen los costes por operación.</InfoTerm>
        <InfoTerm term="Trades">tamaño de la muestra. Con &lt;30 trades, ninguna métrica es fiable; el fitness lo descuenta automáticamente.</InfoTerm>
        <InfoTerm term="Fitness">puntuación compuesta (Sharpe, Sortino, profit factor, Calmar, nº de trades) usada por el optimizador; ≈0.3+ es decente, negativa = descartar.</InfoTerm>
        <InfoH>Señales de alerta</InfoH>
        <p className="text-slate-400">
          Desconfía de: métricas espectaculares con pocos trades, equity que gana todo en un solo
          tramo, y parámetros muy finos (p. ej. sl_atr=9.57): suelen ser sobreajuste. Valida
          siempre con walk-forward antes de operar en real.
        </p>
      </>
    ),
  },

  optimize: {
    title: "Optimización y validación",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          <strong>Optimization</strong> explora el espacio de parámetros de una estrategia (con
          Optuna) buscando maximizar el fitness sobre el histórico. <strong>Validation</strong>{" "}
          comprueba si ese resultado es real o sobreajuste.
        </p>
        <InfoH>Cómo se usa</InfoH>
        <p className="mb-3">
          Lanza una optimización (elige estrategia, dataset y nº de trials). Con el mejor resultado,
          corre las tres validaciones antes de considerarlo operable. El botón{" "}
          <em>Send to auto-trader</em> traslada los parámetros ganadores al trading automático.
        </p>
        <InfoH>Cómo interpretar las validaciones</InfoH>
        <InfoTerm term="Walk-Forward">optimiza en un tramo (in-sample) y prueba en el siguiente sin re-optimizar (out-of-sample), rodando por todo el histórico. Es el estándar de oro: si el OOS aguanta (idealmente &gt;50% del rendimiento IS), la estrategia generaliza.</InfoTerm>
        <InfoTerm term="Monte Carlo">remuestrea el orden de los trades 1000 veces para ver la distribución de resultados posibles. Mira el percentil 5: si incluso ahí sobrevives, el riesgo de ruina es bajo.</InfoTerm>
        <InfoTerm term="Stress test">re-corre el backtest con costes hostiles (más spread, slippage, retraso de ejecución). Si deja de ser rentable con costes realistas-pesimistas, no lo operes.</InfoTerm>
        <p className="mt-3 text-slate-400">
          Regla práctica: solo pasa al auto-trader lo que sobreviva a las tres. Un fitness alto sin
          validación es la receta clásica para perder dinero en vivo.
        </p>
      </>
    ),
  },

  ml: {
    title: "Machine Learning",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Entrenamiento de modelos de ML sobre los datasets: clasificadores con features técnicas
          (importancia de variables incluida) y un agente de refuerzo (PPO) que aprende una
          política de trading.
        </p>
        <InfoH>Cómo se usa</InfoH>
        <p className="mb-3">
          Elige dataset y tipo de modelo y pulsa <em>Train model</em>. El entrenamiento corre en el
          worker en segundo plano; el estado y las métricas aparecen en la tabla al terminar.
        </p>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="Accuracy / F1">calidad de clasificación fuera de muestra. En mercados, apenas superar el 50% ya puede ser útil si la gestión de riesgo acompaña.</InfoTerm>
        <InfoTerm term="Top features">qué variables pesan más en el modelo — útil para entender qué está &quot;mirando&quot;.</InfoTerm>
        <InfoH>Cómo se usan de verdad (meta-labeling)</InfoH>
        <p className="mb-2">
          Un modelo de tipo <strong>win</strong> se puede usar como <strong>filtro de entrada</strong>{" "}
          de cualquier estrategia: en el Backtest, elige el modelo en «Filtro ML» y activa{" "}
          <em>use_ml_filter</em> con un <em>ml_threshold</em>. La estrategia solo tomará las
          entradas donde el modelo prediga alta probabilidad de ganar — menos operaciones, pero de
          más calidad. El mismo filtro viaja al auto-trader (badge «ML» en la tabla).
        </p>
        <p className="text-slate-400">
          Calibra el umbral a cada modelo: si se entrenó con TP lejano, su P(ganar) es baja y
          umbrales de 0.20-0.30 ya filtran mucho. Y trata los modelos con el mismo escepticismo que
          una estrategia optimizada: valida out-of-sample antes de darles dinero real.
        </p>
      </>
    ),
  },

  trading: {
    title: "Trading y auto-traders",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Ejecución real contra tu cuenta del broker. <strong>Trading</strong> muestra la cuenta
          (balance, NAV, posiciones) y permite evaluar/ejecutar una señal manualmente.{" "}
          <strong>Automated trading</strong> lista los auto-traders: asignaciones
          estrategia+símbolo+timeframe que un worker dedicado ejecuta solo, vela a vela.
        </p>
        <InfoH>Cómo se usa</InfoH>
        <InfoTerm term="Kill switch">interruptor global. Apagado = nada opera (ni manual ni automático). En entorno live exige escribir TRADE-LIVE para activarse.</InfoTerm>
        <InfoTerm term="Evaluate & execute">evalúa la última vela cerrada de una estrategia y ejecuta su señal si la hay — mismo camino de código que usa el auto-trader.</InfoTerm>
        <InfoTerm term="Auto-traders">se crean desde Backtest/Results/Optimization con «Send to auto-trader». Actívalos individualmente; el worker los evalúa al cierre real de cada vela de su timeframe.</InfoTerm>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="Last action">qué hizo en la última vela evaluada: opened_long/short (abrió), closed (cerró por señal contraria), none (sin señal).</InfoTerm>
        <InfoTerm term="Unrealized P/L">ganancia/pérdida flotante de cada posición abierta. Las salidas las gestionan el SL/TP (o trailing stop) colocados en el broker al abrir.</InfoTerm>
        <InfoTerm term="Message">si algo falla (broker caído, estrategia mal configurada) el error queda aquí y se reintenta en la siguiente vela.</InfoTerm>
        <InfoTerm term="Trade history">registro local de cada ejecución: qué estrategia disparó, precio de entrada real (fill del broker), niveles SL/TP colocados, P/L realizado en cierres y los parámetros exactos de la estrategia en ese momento (hover sobre la fila).</InfoTerm>
        <p className="mt-3 text-slate-400">
          Seguridad: empieza siempre en practice, con units pequeñas, y solo tras validar la
          estrategia. El entorno (practice/live) se configura en Ajustes.
        </p>
      </>
    ),
  },

  logs: {
    title: "Logs",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Registro en vivo de lo que hacen la API, el worker y el auto-trader (via Redis). Es el
          primer sitio donde mirar si algo no se comporta como esperas.
        </p>
        <InfoH>Cómo interpretarlo</InfoH>
        <InfoTerm term="source=autotrader">actividad del trading automático: heartbeats por tick, velas evaluadas y órdenes ejecutadas.</InfoTerm>
        <InfoTerm term="WARNING con «Executed …»">se envió una orden real al broker — cada operación abierta/cerrada deja esta traza.</InfoTerm>
        <InfoTerm term="ERROR / exception">algo falló; el mensaje incluye el detalle. Los fallos transitorios (broker inalcanzable) se reintentan solos.</InfoTerm>
      </>
    ),
  },

  settings: {
    title: "Ajustes del broker",
    body: (
      <>
        <InfoH>Qué es</InfoH>
        <p className="mb-3">
          Credenciales de OANDA que usa toda la plataforma: token de API, cuenta y entorno
          (practice = dinero ficticio, live = dinero real).
        </p>
        <InfoH>Cómo se usa</InfoH>
        <p className="mb-3">
          Pega el token generado en tu cuenta de OANDA, verifica la conexión y selecciona la
          cuenta. El entorno que elijas aquí es el que usan los datos, el trading manual y el
          auto-trader.
        </p>
        <p className="text-slate-400">
          Cambiar a live no activa nada por sí solo (el kill switch sigue mandando), pero a partir
          de ahí toda orden ejecutada es dinero real. Hazlo solo con estrategias validadas.
        </p>
      </>
    ),
  },
};

export function SectionInfoButton({ menu }: { menu: string }) {
  const info = SECTION_INFO[menu];
  if (!info) return null;
  return <InfoModal title={info.title}>{info.body}</InfoModal>;
}
