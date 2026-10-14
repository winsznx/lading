const MINUS = "−";

const INDIAN_GROUPING = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const THOUSANDS = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const THOUSANDS_1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function sign(value: number, explicitPlus: boolean): string {
  if (value < 0) return MINUS;
  if (value > 0 && explicitPlus) return "+";
  return "";
}

function rounded(value: number, digits: number): number {
  const factor = 10 ** digits;
  const r = Math.round(value * factor) / factor;
  return Object.is(r, -0) ? 0 : r;
}

/** ₹17,44,891 — Indian digit grouping, whole rupees. */
export function formatInr(value: number): string {
  const r = rounded(value, 0);
  return `${sign(r, false)}₹${INDIAN_GROUPING.format(Math.abs(r))}`;
}

/** +₹1,21,016 / −₹4,200 / ₹0 */
export function formatInrDelta(value: number): string {
  const r = rounded(value, 0);
  return `${sign(r, true)}₹${INDIAN_GROUPING.format(Math.abs(r))}`;
}

export function formatNumber(value: number, digits = 0): string {
  const r = rounded(value, digits);
  const body = digits === 1 ? THOUSANDS_1.format(Math.abs(r)) : THOUSANDS.format(Math.abs(r));
  return `${sign(r, false)}${body}`;
}

export function formatKg(value: number): string {
  return `${formatNumber(value)} kg`;
}

export function formatKgDelta(value: number): string {
  const r = rounded(value, 0);
  return `${sign(r, true)}${THOUSANDS.format(Math.abs(r))} kg`;
}

/** 26h, 25.5h */
export function formatHours(hours: number): string {
  const r = rounded(hours, 1);
  const whole = Number.isInteger(r);
  return `${sign(r, false)}${whole ? Math.abs(r).toString() : Math.abs(r).toFixed(1)}h`;
}

export function formatHoursDelta(hours: number): string {
  const r = rounded(hours, 1);
  return `${sign(r, true)}${formatHours(Math.abs(r))}`;
}

export function formatPct(value: number, digits = 1): string {
  const r = rounded(value, digits);
  return `${sign(r, false)}${Math.abs(r).toFixed(digits)}%`;
}

/** Percentage-point delta: +2.1 pp */
export function formatPp(value: number, digits = 1): string {
  const r = rounded(value, digits);
  return `${sign(r, true)}${Math.abs(r).toFixed(digits)} pp`;
}

export function formatSeconds(seconds: number): string {
  return `${rounded(seconds, 1).toFixed(1)}s`;
}

/** A discount fraction as shown on a price chip: 0.1 -> "10% off" */
export function formatDiscount(fraction: number): string {
  return `${Math.round(fraction * 100)}% off`;
}

export function formatRatio(value: number): string {
  return `${rounded(value, 2)}×`;
}

export function shortMarket(name: string): string {
  return name.split(" (")[0] ?? name;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}
