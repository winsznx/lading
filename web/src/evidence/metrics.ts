import type { MetricKey } from "../api/types";
import { formatInrDelta, formatKgDelta, formatPp } from "../lib/format";

export const METRICS: { key: MetricKey; label: string; better: "lower" | "higher" }[] = [
  { key: "spoiled_kg", label: "Spoiled", better: "lower" },
  { key: "demand_filled_pct", label: "Demand filled", better: "higher" },
  { key: "net_inr", label: "Net", better: "higher" },
];

export function formatMetricDelta(key: MetricKey, value: number): string {
  if (key === "spoiled_kg") return formatKgDelta(value);
  if (key === "demand_filled_pct") return formatPp(value);
  return formatInrDelta(value);
}

export function deltaTone(key: MetricKey, value: number): string {
  if (Math.abs(value) < 1e-9) return "text-ink-2";
  const good = key === "spoiled_kg" ? value < 0 : value > 0;
  return good ? "text-good" : "text-bad";
}
