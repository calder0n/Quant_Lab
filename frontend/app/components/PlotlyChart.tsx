"use client";

import { useEffect, useRef } from "react";

const BASE_LAYOUT: Record<string, unknown> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", size: 10, family: "ui-sans-serif, system-ui" },
  margin: { t: 28, r: 12, b: 36, l: 52 },
  xaxis: { gridcolor: "rgba(51,65,85,0.4)", zerolinecolor: "rgba(51,65,85,0.6)" },
  yaxis: { gridcolor: "rgba(51,65,85,0.4)", zerolinecolor: "rgba(51,65,85,0.6)" },
};

export default function PlotlyChart({
  data,
  layout = {},
  height = 260,
}: {
  data: unknown[];
  layout?: Record<string, unknown>;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    let cancelled = false;
    import("plotly.js-dist-min").then((Plotly) => {
      if (cancelled || !node) return;
      const merged = {
        ...BASE_LAYOUT,
        ...layout,
        xaxis: { ...(BASE_LAYOUT.xaxis as object), ...((layout.xaxis as object) ?? {}) },
        yaxis: { ...(BASE_LAYOUT.yaxis as object), ...((layout.yaxis as object) ?? {}) },
        height,
      };
      Plotly.newPlot(node, data, merged, { displayModeBar: false, responsive: true });
    });
    return () => {
      cancelled = true;
      if (node) import("plotly.js-dist-min").then((Plotly) => Plotly.purge(node));
    };
  }, [data, layout, height]);

  return <div ref={ref} style={{ height }} />;
}
