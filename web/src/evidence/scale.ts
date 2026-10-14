export interface Linear {
  (value: number): number;
  ticks: number[];
}

function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const residual = raw / magnitude;
  const nice = residual >= 5 ? 10 : residual >= 2 ? 5 : residual >= 1 ? 2 : 1;
  return nice * magnitude;
}

/** Linear scale over a domain widened to round tick values. */
export function linear(domain: [number, number], range: [number, number], tickCount = 5): Linear {
  let [lo, hi] = domain;
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.1 || 1;
    lo -= pad;
    hi += pad;
  }
  const step = niceStep(hi - lo, tickCount);
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let t = start; t <= end + step / 2; t += step) ticks.push(Math.round(t / step) * step);
  const [r0, r1] = range;
  return Object.assign((value: number) => r0 + ((value - start) / (end - start)) * (r1 - r0), { ticks });
}

export function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
