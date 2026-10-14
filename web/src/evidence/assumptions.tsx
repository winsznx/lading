import type { ReactElement } from "react";

import type { Assumptions } from "../api/types";

interface Row {
  key: string;
  label: string;
  value: string;
  unit: string;
  numeric: boolean;
}

/** Unit carried in a key name, and what the label reads once the unit is lifted out of it. */
const UNIT_TOKENS: [RegExp, string, string][] = [
  [/_inr_per_kg/, "₹/kg", ""],
  [/_inr$/, "₹", ""],
  [/_kg_step$/, "kg", "_step"],
  [/_kg$/, "kg", ""],
  [/_h_ago$/, "h", "_(hours_ago)"],
  [/_h$/, "h", ""],
  [/_pct$/, "%", ""],
  [/_frac$/, "fraction", ""],
];

function sentence(key: string): string {
  const words = key.replace(/^n_/, "number_of_").replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function describeKey(key: string): { label: string; unit: string } {
  for (const [pattern, unit, replacement] of UNIT_TOKENS) {
    if (!pattern.test(key)) continue;
    const money = unit.startsWith("₹") && !/price|cost/.test(key);
    return { label: sentence(key.replace(pattern, money ? `_cost${replacement}` : replacement)), unit };
  }
  return { label: sentence(key), unit: "" };
}

function humanize(key: string): string {
  return describeKey(key).label;
}

function scalar(value: unknown): string | null {
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("en-US") : String(value);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value === null) return "none";
  if (Array.isArray(value) && value.every((v) => typeof v === "number")) {
    const nums = value.map((v) => (Number.isInteger(v) ? v.toLocaleString("en-US") : String(v)));
    return nums.length === 2 ? `${nums[0] ?? ""} to ${nums[1] ?? ""}` : nums.join(" · ");
  }
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) return value.join(", ");
  return null;
}

function flatten(value: unknown, path: string[], out: Row[]): void {
  const leafKey = path[path.length - 1] ?? "";
  const text = scalar(value);
  if (text !== null) {
    const numeric = typeof value === "number" || (Array.isArray(value) && value.every((v) => typeof v === "number"));
    const { label, unit } = describeKey(leafKey);
    out.push({ key: path.join("."), label, value: text, unit, numeric });
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, i) => {
      const record = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : null;
      const name = record && typeof record.id === "string" ? record.id : String(i);
      flatten(item, [...path, name], out);
    });
    return;
  }
  if (typeof value === "object" && value !== null) {
    for (const [k, v] of Object.entries(value)) flatten(v, [...path, k], out);
  }
}

interface Group {
  name: string;
  rows: Row[];
}

function groups(data: Assumptions): Group[] {
  const top: Row[] = [];
  const nested: Group[] = [];
  for (const [key, value] of Object.entries(data)) {
    const rows: Row[] = [];
    flatten(value, [key], rows);
    if (rows.length === 1 && rows[0]?.key === key) top.push(...rows);
    else nested.push({ name: key, rows });
  }
  return [{ name: "general", rows: top }, ...nested];
}

function RowsTable({ rows, prefix }: { rows: Row[]; prefix: string }): ReactElement {
  return (
    <table className="w-full table-fixed text-13">
      <colgroup>
        <col className="w-[44%]" />
        <col />
        <col className="w-20" />
      </colgroup>
      <thead className="sr-only">
        <tr>
          <th>Assumption</th>
          <th>Value</th>
          <th>Unit</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const context = row.key
            .split(".")
            .slice(prefix ? 1 : 0, -1)
            .join(" › ");
          return (
            <tr key={row.key} className="align-baseline">
              <th scope="row" className="border-t border-line py-1 pr-3 text-left font-normal text-ink-2">
                {context ? <span className="num text-12 text-ink-3">{context} › </span> : null}
                {row.label}
              </th>
              {row.numeric ? (
                <>
                  <td className="num border-t border-line py-1 pr-3 text-right text-ink">{row.value}</td>
                  <td className="border-t border-line py-1 text-12 text-ink-3">{row.unit}</td>
                </>
              ) : (
                <td colSpan={2} className="border-t border-line py-1 text-left text-ink">
                  {row.value}
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function AssumptionsTable({ data }: { data: Assumptions }): ReactElement {
  const all = groups(data);
  return (
    <div className="flex flex-col gap-4">
      {all.map((group) => {
        if (group.rows.length === 0) return null;
        if (group.name === "general") {
          const half = Math.ceil(group.rows.length / 2);
          return (
            <div key={group.name} className="grid gap-x-8 xl:grid-cols-2">
              <RowsTable rows={group.rows.slice(0, half)} prefix="" />
              <RowsTable rows={group.rows.slice(half)} prefix="" />
            </div>
          );
        }
        if (group.rows.length <= 12) {
          return (
            <div key={group.name}>
              <h3 className="text-12 font-semibold text-ink">{humanize(group.name)}</h3>
              <RowsTable rows={group.rows} prefix={group.name} />
            </div>
          );
        }
        return (
          <details key={group.name}>
            <summary className="cursor-pointer text-12 font-semibold text-ink">
              {humanize(group.name)} <span className="font-normal text-ink-3">({group.rows.length} values)</span>
            </summary>
            <div className="mt-1">
              <RowsTable rows={group.rows} prefix={group.name} />
            </div>
          </details>
        );
      })}
    </div>
  );
}
