import type { ReactElement } from "react";

import type { SensitivityResults } from "../api/types";
import { armName } from "../lib/codes";
import { formatInrDelta, formatNumber, formatRatio } from "../lib/format";
import { useWidth } from "../lib/use-width";
import { linear } from "./scale";

const HEIGHT = 260;
const PAD = { left: 108, right: 24, top: 16, bottom: 48 };

function takeaway(data: SensitivityResults): string {
  const points = data.points.toSorted((a, b) => a.factor - b.factor);
  const name = armName(data.arm);
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return "No sensitivity points in the file.";
  const losing = points.filter((p) => p.net_inr.median <= 0);
  if (losing.length === 0) {
    return `${name} keeps a positive median net gain over FEFO at every elasticity tested: ${formatInrDelta(first.net_inr.median)} at ${formatRatio(first.factor)} to ${formatInrDelta(last.net_inr.median)} at ${formatRatio(last.factor)}.`;
  }
  if (losing.length === points.length) {
    return `${name} has no positive median net gain over FEFO at any elasticity tested, from ${formatRatio(first.factor)} to ${formatRatio(last.factor)}.`;
  }
  const worst = losing.reduce((a, b) => (b.net_inr.median < a.net_inr.median ? b : a));
  return `${name}'s median net gain over FEFO turns negative at ${losing.map((p) => formatRatio(p.factor)).join(", ")} the disclosed elasticity, lowest ${formatInrDelta(worst.net_inr.median)} at ${formatRatio(worst.factor)}.`;
}

export function SensitivityChart({ data }: { data: SensitivityResults }): ReactElement {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const points = data.points.toSorted((a, b) => a.factor - b.factor);
  const line = takeaway(data);
  if (points.length === 0) {
    return <p className="text-13 text-ink-2">{line}</p>;
  }

  const factors = points.map((p) => p.factor);
  const lows = points.map((p) => Math.min(p.net_inr.q1, p.net_inr.median));
  const highs = points.map((p) => Math.max(p.net_inr.q3, p.net_inr.median));
  const x = linear([Math.min(...factors), Math.max(...factors)], [PAD.left, width - PAD.right], 5);
  const y = linear([Math.min(0, ...lows), Math.max(0, ...highs)], [HEIGHT - PAD.bottom, PAD.top], 5);
  const xTicks = factors;

  const band = [
    ...points.map((p) => `${x(p.factor)},${y(p.net_inr.q3)}`),
    ...points.toReversed().map((p) => `${x(p.factor)},${y(p.net_inr.q1)}`),
  ].join(" ");
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.factor)},${y(p.net_inr.median)}`).join(" ");

  return (
    <figure className="rounded border border-line bg-surface p-3">
      <figcaption className="text-13 text-ink">{line}</figcaption>
      <div ref={ref} className="mt-3 w-full">
        <svg width={width} height={HEIGHT} role="img" aria-label={line} className="block">
          {y.ticks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(t)}
                y2={y(t)}
                stroke={t === 0 ? "var(--ink-2)" : "var(--line)"}
              />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize={12} className="num" fill="var(--ink-3)">
                {formatInrDelta(t)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <g key={t}>
              <line
                x1={x(t)}
                x2={x(t)}
                y1={HEIGHT - PAD.bottom}
                y2={HEIGHT - PAD.bottom + 4}
                stroke="var(--line-strong)"
              />
              <text
                x={x(t)}
                y={HEIGHT - PAD.bottom + 18}
                textAnchor="middle"
                fontSize={12}
                className="num"
                fill="var(--ink-3)"
              >
                {formatRatio(t)}
              </text>
            </g>
          ))}
          <polygon points={band} fill="var(--lading-wash)" stroke="none" />
          <path d={path} fill="none" stroke="var(--lading)" strokeWidth={2} />
          {points.map((p) => (
            <circle key={p.factor} cx={x(p.factor)} cy={y(p.net_inr.median)} r={3.5} fill="var(--lading)">
              <title>{`${formatRatio(p.factor)}: median ${formatInrDelta(p.net_inr.median)}, IQR ${formatInrDelta(p.net_inr.q1)} to ${formatInrDelta(p.net_inr.q3)}, wins ${p.net_inr.wins}/${p.net_inr.n}`}</title>
            </circle>
          ))}
          <text
            x={(PAD.left + width - PAD.right) / 2}
            y={HEIGHT - 6}
            textAnchor="middle"
            fontSize={12}
            fill="var(--ink-2)"
          >
            {width < 560
              ? "Realized elasticity (× disclosed)"
              : "Realized elasticity, multiple of the disclosed value (×)"}
          </text>
          <text
            transform={`translate(12 ${(PAD.top + HEIGHT - PAD.bottom) / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize={12}
            fill="var(--ink-2)"
          >
            Median paired net gain vs FEFO (₹)
          </text>
        </svg>
      </div>
      <p className="mt-2 text-12 text-ink-3">
        Line: median over held-out days. Band: interquartile range. Arm: {armName(data.arm)}.
        {data.note ? ` ${data.note}` : ""}
      </p>
      <table className="mt-3 w-full text-12">
        <caption className="sr-only">Sensitivity points</caption>
        <thead>
          <tr className="text-ink-2">
            <th scope="col" className="border-b border-line px-2 py-1 text-left font-medium">
              Elasticity
            </th>
            <th scope="col" className="border-b border-line px-2 py-1 text-right font-medium">
              Median net gain
            </th>
            <th scope="col" className="border-b border-line px-2 py-1 text-right font-medium">
              IQR
            </th>
            <th scope="col" className="border-b border-line px-2 py-1 text-right font-medium">
              Wins
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.factor}>
              <td className="num border-b border-line px-2 py-1 text-ink">{formatRatio(p.factor)}</td>
              <td className="num border-b border-line px-2 py-1 text-right text-ink">
                {formatInrDelta(p.net_inr.median)}
              </td>
              <td className="num border-b border-line px-2 py-1 text-right text-ink-2">
                {formatInrDelta(p.net_inr.q1)} to {formatInrDelta(p.net_inr.q3)}
              </td>
              <td className="num border-b border-line px-2 py-1 text-right text-ink-2">
                {formatNumber(p.net_inr.wins)}/{formatNumber(p.net_inr.n)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
