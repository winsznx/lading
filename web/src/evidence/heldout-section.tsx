import { type ReactElement, useMemo, useState } from "react";

import type { HeldoutResults, MetricKey, ResultRow } from "../api/types";
import { SortIcon } from "../components/icons";
import { Tag } from "../components/primitives";
import { armName } from "../lib/codes";
import { cx } from "../lib/cx";
import { formatKg, formatNumber } from "../lib/format";
import { DeltaStrip } from "./delta-strip";
import { METRICS, deltaTone, formatMetricDelta } from "./metrics";
import { QuartileCell } from "./shared";

type SortKey = "seed" | "hub" | "batches" | "stock_kg" | MetricKey | "validator";

interface Sort {
  key: SortKey;
  dir: "asc" | "desc";
}

function sortValue(row: ResultRow, key: SortKey, arm: string): number | string {
  switch (key) {
    case "seed":
      return row.seed;
    case "hub":
      return row.hub;
    case "batches":
      return row.batches;
    case "stock_kg":
      return row.stock_kg;
    case "validator":
      return row.arms[arm]?.violations ?? 0;
    default:
      return row.delta[arm]?.[key] ?? 0;
  }
}

function SortHeader({
  label,
  column,
  sort,
  onSort,
  align = "right",
}: {
  label: string;
  column: SortKey;
  sort: Sort;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}): ReactElement {
  const active = sort.key === column;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cx(
        "sticky top-0 z-10 border-b border-line bg-surface px-2 py-2 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      <button
        type="button"
        onClick={() => {
          onSort(column);
        }}
        className={cx(
          "inline-flex items-center gap-1 rounded-sm text-12 hover:text-ink",
          active ? "text-ink" : "text-ink-2",
          align === "right" && "flex-row-reverse",
        )}
      >
        <SortIcon activeOrder={active ? sort.dir : null} />
        {label}
      </button>
    </th>
  );
}

export function HeldoutSection({ data }: { data: HeldoutResults }): ReactElement {
  const deltaArms = useMemo(() => {
    const seen = new Set<string>();
    for (const row of data.rows) for (const arm of Object.keys(row.delta)) seen.add(arm);
    return [...seen].sort((a, b) => (a === data.headline_arm ? -1 : b === data.headline_arm ? 1 : a.localeCompare(b)));
  }, [data]);
  const [arm, setArm] = useState(data.headline_arm);
  const [sort, setSort] = useState<Sort>({ key: "seed", dir: "asc" });

  const rows = useMemo(() => {
    const factor = sort.dir === "asc" ? 1 : -1;
    return data.rows.toSorted((a, b) => {
      const va = sortValue(a, sort.key, arm);
      const vb = sortValue(b, sort.key, arm);
      if (typeof va === "string" || typeof vb === "string") return String(va).localeCompare(String(vb)) * factor;
      return (va - vb) * factor || a.seed - b.seed;
    });
  }, [data.rows, sort, arm]);

  function onSort(key: SortKey): void {
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "seed" || key === "hub" ? "asc" : "desc" },
    );
  }

  const summary = data.summary[arm];
  const firstSeed = data.seeds[0];
  const lastSeed = data.seeds[data.seeds.length - 1];

  return (
    <div className="flex flex-col gap-5">
      <p className="text-13 text-ink-2">
        <span className="num">{formatNumber(data.rows.length)}</span> held-out days
        {firstSeed !== undefined && lastSeed !== undefined ? (
          <>
            {" "}
            (seeds <span className="num">{firstSeed}</span>–<span className="num">{lastSeed}</span>)
          </>
        ) : null}
        , each executed on <span className="num">{formatNumber(data.draws_per_scenario)}</span> realized days. Deltas
        are the arm minus FEFO on the same day; a win is less spoiled, more demand filled or more net.
      </p>

      {deltaArms.length > 1 ? (
        <div role="radiogroup" aria-label="Arm compared with FEFO" className="flex flex-wrap gap-1">
          {deltaArms.map((a) => (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={a === arm}
              onClick={() => {
                setArm(a);
              }}
              className={cx(
                "h-7 rounded-sm border px-2 text-12",
                a === arm
                  ? "border-ink bg-highlight font-medium text-ink"
                  : "border-line text-ink-2 hover:bg-highlight",
              )}
            >
              {armName(a)} − FEFO
              {a === data.headline_arm ? <span className="text-ink-3"> · headline</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      {summary ? (
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {METRICS.map((m) => {
            const q = summary[m.key];
            return (
              <div key={m.key} className="rounded border border-line bg-surface p-3">
                <dt className="text-12 text-ink-2">
                  {m.label}, {armName(arm)} − FEFO <span className="text-ink-3">({m.better} is better)</span>
                </dt>
                <dd className={cx("num mt-1 text-20 font-semibold", deltaTone(m.key, q.median))}>
                  {formatMetricDelta(m.key, q.median)}
                </dd>
                <dd className="mt-0.5 text-12 text-ink-3">
                  median · IQR <span className="num">{formatMetricDelta(m.key, q.q1)}</span> to{" "}
                  <span className="num">{formatMetricDelta(m.key, q.q3)}</span>
                </dd>
                <dd className="text-12 text-ink-3">
                  wins on <span className="num">{formatNumber(q.wins)}</span> of{" "}
                  <span className="num">{formatNumber(q.n)}</span> days
                </dd>
              </div>
            );
          })}
        </dl>
      ) : null}

      <DeltaStrip rows={data.rows} arm={arm} metric="net_inr" />

      {Object.keys(data.summary).length > 1 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-13">
            <caption className="pb-2 text-left text-12 text-ink-3">
              Every arm against FEFO: median, interquartile range, wins.
            </caption>
            <thead>
              <tr className="text-12 text-ink-2">
                <th scope="col" className="border-b border-line px-2 py-2 text-left font-medium">
                  Arm
                </th>
                {METRICS.map((m) => (
                  <th key={m.key} scope="col" className="border-b border-line px-2 py-2 text-right font-medium">
                    Δ {m.label.toLowerCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.summary)
                .filter(([name]) => name !== "fefo")
                .map(([name, s]) => (
                  <tr key={name} className="align-top">
                    <th scope="row" className="border-b border-line px-2 py-2 text-left font-medium text-ink">
                      {armName(name)}
                    </th>
                    {METRICS.map((m) => (
                      <td key={m.key} className="border-b border-line px-2 py-2">
                        <QuartileCell metric={m.key} q={s[m.key]} />
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="scroll-quiet max-h-[560px] overflow-auto rounded border border-line">
        <table className="w-full min-w-[720px] border-collapse whitespace-nowrap text-13">
          <caption className="sr-only">
            Paired deltas per held-out day, {armName(arm)} minus FEFO. Sortable by column.
          </caption>
          <thead>
            <tr>
              <SortHeader label="Seed" column="seed" sort={sort} onSort={onSort} align="left" />
              <SortHeader label="Hub" column="hub" sort={sort} onSort={onSort} align="left" />
              <SortHeader label="Batches" column="batches" sort={sort} onSort={onSort} />
              <SortHeader label="Stock" column="stock_kg" sort={sort} onSort={onSort} />
              <SortHeader label="Δ spoiled" column="spoiled_kg" sort={sort} onSort={onSort} />
              <SortHeader label="Δ demand filled" column="demand_filled_pct" sort={sort} onSort={onSort} />
              <SortHeader label="Δ net" column="net_inr" sort={sort} onSort={onSort} />
              <SortHeader label="Validator" column="validator" sort={sort} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const delta = row.delta[arm];
              const result = row.arms[arm];
              return (
                <tr key={row.seed} className="hover:bg-highlight">
                  <td className="num border-b border-line px-2 py-1 text-ink">{row.seed}</td>
                  <td className="border-b border-line px-2 py-1 text-ink-2">{row.hub}</td>
                  <td className="num border-b border-line px-2 py-1 text-right text-ink-2">{row.batches}</td>
                  <td className="num border-b border-line px-2 py-1 text-right text-ink-2">{formatKg(row.stock_kg)}</td>
                  {METRICS.map((m) => (
                    <td
                      key={m.key}
                      className={cx(
                        "num border-b border-line px-2 py-1 text-right",
                        delta ? deltaTone(m.key, delta[m.key]) : "text-ink-3",
                      )}
                    >
                      {delta ? formatMetricDelta(m.key, delta[m.key]) : "no data"}
                    </td>
                  ))}
                  <td className="border-b border-line px-2 py-1 text-right">
                    {result ? (
                      <Tag tone={result.validator === "PASS" ? "good" : "bad"}>
                        {result.validator === "PASS" ? "pass" : `${formatNumber(result.violations)} violations`}
                      </Tag>
                    ) : (
                      <span className="text-12 text-ink-3">no data</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
