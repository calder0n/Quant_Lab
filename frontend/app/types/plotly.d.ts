declare module "plotly.js-dist-min" {
  export function newPlot(
    root: HTMLElement,
    data: unknown[],
    layout?: Record<string, unknown>,
    config?: Record<string, unknown>,
  ): Promise<void>;
  export function purge(root: HTMLElement): void;
}
