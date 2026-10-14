import type { ReactElement } from "react";

import type { MetricKey, ResultRow } from "../api/types";
import { armName } from "../lib/codes";
import { formatInrDelta, formatNumber } from "../lib/format";
import { useWidth } from "../lib/use-width";
import { formatMetricDelta } from "./metrics";
import { linear } from "./scale";

const HEIGHT = 112;
const PAD = { left: 24, right: 48, top: 12, bottom: 36 };

function median(values: number[]): number {
  const sorted = values.toSorted((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const hi = sorted[mid] ?? 0;
  const lo = sorted[mid - 1] ?? hi;
  return sorted.length % 2 === 0 ? (lo + hi) / 2 : hi;
}

/** One dot per held-out day: the paired net gain of the chosen arm over FEFO. */
export function DeltaStrip({
  rows,
  arm,
  metric,
}: {
  rows: ResultRow[];
  arm: string;
  metric: MetricKey;
}): ReactElement | null {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const points = rows.flatMap((row) => {
    const value = row.delta[arm]?.[metric];
    return value === undefined ? [] : [{ seed: row.seed, value }];
  });
  if (points.length === 0) return null;

  const values = points.map((p) => p.value);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const x = linear([lo, hi], [PAD.left, width - PAD.right], width < 480 ? 3 : 6);
  const mid = median(values);
  const wins = values.filter((v) => (metric === "spoiled_kg" ? v < 0 : v > 0)).length;
  const baseline = HEIGHT - PAD.bottom;

  const stacks = new Map<number, number>();
  const leveled = points.map((p) => {
    const px = x(p.value);
    const bucket = Math.round(px / 6);
    const level = stacks.get(bucket) ?? 0;
    stacks.set(bucket, level + 1);
    return { ...p, px, level };
  });
  const tallest = Math.max(1, ...leveled.map((p) => p.level));
  const step = Math.min(6, (baseline - 8 - PAD.top) / tallest);
  const placed = leveled.map((p) => ({ ...p, py: baseline - 8 - p.level * step }));

  const takeaway =
    metric === "net_inr"
      ? `${armName(arm)} earned more net than FEFO on ${formatNumber(wins)} of ${formatNumber(points.length)} days; the median day gained ${formatInrDelta(mid)}.`
      : `${armName(arm)} beat FEFO on ${formatNumber(wins)} of ${formatNumber(points.length)} days; median ${formatMetricDelta(metric, mid)}.`;

  return (
    <figure className="rounded border border-line bg-surface p-3">
      <figcaption className="text-13 text-ink">{takeaway}</figcaption>
      <div ref={ref} className="mt-2 w-full">
        <svg width={width} height={HEIGHT} role="img" aria-label={takeaway} className="block overflow-visible">
          {x.ticks.map((t) => (
            <g key={t} transform={`translate(${x(t)},0)`}>
              <line y1={PAD.top} y2={baseline} stroke="var(--line)" />
              <text y={baseline + 16} textAnchor="middle" className="num" fontSize={12} fill="var(--ink-3)">
                {formatMetricDelta(metric, t)}
              </text>
            </g>
          ))}
          <line x1={x(0)} x2={x(0)} y1={PAD.top - 4} y2={baseline} stroke="var(--ink-2)" />
          <line x1={PAD.left} x2={width - PAD.right} y1={baseline} y2={baseline} stroke="var(--line-strong)" />
          {placed.map((p) => (
            <circle key={p.seed} cx={p.px} cy={p.py} r={2.5} fill="var(--lading)">
              <title>{`seed ${p.seed}: ${formatMetricDelta(metric, p.value)}`}</title>
            </circle>
          ))}
          <line x1={x(mid)} x2={x(mid)} y1={PAD.top - 4} y2={baseline} stroke="var(--ink)" strokeDasharray="3 2" />
          <text x={x(mid) + 4} y={PAD.top + 4} fontSize={12} fill="var(--ink)">
            median
          </text>
          <text x={width - PAD.right} y={HEIGHT - 4} textAnchor="end" fontSize={12} fill="var(--ink-3)">
            {metric === "net_inr" ? "paired net gain vs FEFO, ₹ per day" : "paired delta vs FEFO per day"}
          </text>
        </svg>
      </div>
    </figure>
  );
}
