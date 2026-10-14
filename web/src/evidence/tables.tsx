import type { ReactElement } from "react";
import type {
  AblationResults,
  CanonicalResults,
  ControlsResults,
  HeldoutResults,
  StressResults,
  TimingStat,
  TimingsResults,
  VerdictResults,
} from "../api/types";
import { NumText, Tag } from "../components/primitives";
import { armName } from "../lib/codes";
import { cx } from "../lib/cx";
import {
  formatInr,
  formatInrDelta,
  formatKg,
  formatKgDelta,
  formatNumber,
  formatPct,
  formatPp,
  formatSeconds,
} from "../lib/format";
import { METRICS } from "./metrics";
import { QuartileCell } from "./shared";

const TH = "border-b border-line px-2 py-2 text-12 font-medium text-ink-2";
const TD = "border-b border-line px-2 py-2 align-top";

export function VerdictPanel({ data }: { data: VerdictResults }): ReactElement {
  const holds = !data.triggered;
  return (
    <div className="rounded-md border border-line-strong bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone={holds ? "good" : "bad"}>{data.verdict}</Tag>
        <span className="text-12 text-ink-2">
          Falsifier {data.triggered ? "triggered" : "not triggered"} · headline arm {armName(data.headline_arm)}
        </span>
      </div>
      <p className="mt-3 max-w-[64ch] text-20 font-medium text-ink">
        <NumText text={data.statement} />
      </p>
      <p className="mt-3 max-w-[72ch] text-13 text-ink-2">
        <span className="text-ink-3">Falsifier: </span>
        <NumText text={data.falsifier} />
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <dt className="text-12 text-ink-3">Median net gain vs FEFO</dt>
          <dd className="num text-16 font-medium text-ink">{formatInrDelta(data.median_net_gain_inr)}</dd>
        </div>
        <div>
          <dt className="text-12 text-ink-3">Median spoiled delta vs FEFO</dt>
          <dd className="num text-16 font-medium text-ink">{formatKgDelta(data.median_spoiled_delta_kg)}</dd>
        </div>
        {data.median_fill_delta_pp !== undefined ? (
          <div>
            <dt className="text-12 text-ink-3">Median demand filled delta</dt>
            <dd className="num text-16 font-medium text-ink">{formatPp(data.median_fill_delta_pp, 2)}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-12 text-ink-3">Validator violations</dt>
          <dd className="num text-16 font-medium text-ink">{formatNumber(data.validator_violations)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function AblationTable({ data }: { data: AblationResults }): ReactElement {
  const entries = Object.entries(data.summary);
  if (entries.length === 0) return <p className="text-13 text-ink-2">The file lists no ablations.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-13">
        <caption className="pb-2 text-left text-12 text-ink-3">
          Each row removes one piece of the planner. Deltas are the ablation minus {armName(data.base_arm)} on the same
          day.
        </caption>
        <thead>
          <tr>
            <th scope="col" className={cx(TH, "text-left")}>
              Ablation
            </th>
            {METRICS.map((m) => (
              <th key={m.key} scope="col" className={cx(TH, "text-right")}>
                Δ {m.label.toLowerCase()}
              </th>
            ))}
            <th scope="col" className={cx(TH, "text-right")}>
              Violations
            </th>
            <th scope="col" className={cx(TH, "text-right")}>
              Plans failing validator
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([name, s]) => (
            <tr key={name}>
              <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
                {armName(name)}
                <span className="block text-12 font-normal text-ink-3">vs {armName(s.vs)}</span>
              </th>
              {METRICS.map((m) => (
                <td key={m.key} className={TD}>
                  <QuartileCell metric={m.key} q={s[m.key]} />
                </td>
              ))}
              <td className={cx(TD, "num text-right text-ink")}>{formatNumber(s.violations)}</td>
              <td className={cx(TD, "num text-right text-ink")}>{formatNumber(s.plans_failing_validator)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StressTable({ data }: { data: StressResults }): ReactElement {
  const families = Object.entries(data.families);
  if (families.length === 0) return <p className="text-13 text-ink-2">The file lists no stress families.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-13">
        <caption className="pb-2 text-left text-12 text-ink-3">
          Each family shocks the realized world. Deltas are each arm minus FEFO on the same day.
        </caption>
        <thead>
          <tr>
            <th scope="col" className={cx(TH, "text-left")}>
              Family and arm
            </th>
            {METRICS.map((m) => (
              <th key={m.key} scope="col" className={cx(TH, "text-right")}>
                Δ {m.label.toLowerCase()}
              </th>
            ))}
          </tr>
        </thead>
        {families.map(([family, f]) => (
          <tbody key={family}>
            <tr>
              <th scope="rowgroup" colSpan={4} className="border-b border-line bg-sunken px-2 py-2 text-left">
                <span className="text-13 font-semibold text-ink">{family.replace(/_/g, " ")}</span>
                <span className="ml-2 text-12 font-normal text-ink-2">{f.description}</span>
                <span className="ml-2 text-12 font-normal text-ink-3">
                  <span className="num">{f.seeds.length}</span> seeds
                </span>
                {f.validator ? (
                  <span className="mt-0.5 block text-12 font-normal text-ink-3">
                    Validator:{" "}
                    {Object.entries(f.validator)
                      .map(([arm, t]) => `${armName(arm)} ${formatNumber(t.pass)} pass, ${formatNumber(t.fail)} fail`)
                      .join("; ")}
                  </span>
                ) : null}
              </th>
            </tr>
            {Object.entries(f.summary)
              .filter(([arm]) => arm !== "fefo")
              .map(([arm, s]) => (
                <tr key={arm}>
                  <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
                    {armName(arm)}
                  </th>
                  {METRICS.map((m) => (
                    <td key={m.key} className={TD}>
                      <QuartileCell metric={m.key} q={s[m.key]} />
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

export function ValidatorTable({ data }: { data: HeldoutResults }): ReactElement {
  const arms = Object.entries(data.validator);
  return (
    <table className="w-full text-13">
      <caption className="pb-2 text-left text-12 text-ink-3">
        Held-out plans re-checked by the independent validator.
      </caption>
      <thead>
        <tr>
          <th scope="col" className={cx(TH, "text-left")}>
            Arm
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Pass
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Fail
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Violations
          </th>
        </tr>
      </thead>
      <tbody>
        {arms.map(([arm, t]) => (
          <tr key={arm}>
            <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
              {armName(arm)}
            </th>
            <td className={cx(TD, "num text-right text-ink")}>{formatNumber(t.pass)}</td>
            <td className={cx(TD, "num text-right", t.fail > 0 ? "text-bad" : "text-ink")}>{formatNumber(t.fail)}</td>
            <td className={cx(TD, "num text-right", t.violations > 0 ? "text-bad" : "text-ink")}>
              {formatNumber(t.violations)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function controlName(key: string): string {
  const match = /^p(\d+)_(.+)$/.exec(key);
  if (match?.[1] && match[2]) return `P${match[1]} ${match[2].replace(/_/g, " ")}`;
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function ControlsList({ data }: { data: ControlsResults }): ReactElement {
  return (
    <ul className="flex flex-col">
      {Object.entries(data).map(([key, check]) => (
        <li key={key} className="flex items-start gap-3 border-t border-line py-2 first:border-t-0">
          <Tag tone={check.passed ? "good" : "bad"}>{check.passed ? "passed" : "failed"}</Tag>
          <div className="min-w-0">
            <p className="text-13 font-medium text-ink">{controlName(key)}</p>
            {check.rule ? <p className="text-12 text-ink-3">{check.rule}</p> : null}
            <p className="text-12 text-ink-2">
              <NumText text={check.detail} />
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function isTimingStat(value: unknown): value is TimingStat {
  return typeof value === "object" && value !== null && typeof (value as Record<string, unknown>).median_s === "number";
}

function timingRows(data: TimingsResults): { name: string; t: TimingStat }[] {
  const rows: { name: string; t: TimingStat }[] = [];
  for (const [group, value] of Object.entries(data)) {
    if (typeof value === "string") continue;
    const label = group.replace(/_/g, " ");
    if (isTimingStat(value)) {
      rows.push({ name: label, t: value });
      continue;
    }
    for (const [arm, stat] of Object.entries(value)) {
      if (isTimingStat(stat)) rows.push({ name: `${armName(arm)}, ${label}`, t: stat });
    }
  }
  return rows;
}

export function TimingsTable({ data }: { data: TimingsResults }): ReactElement {
  const rows = timingRows(data);
  const note = typeof data.note === "string" ? data.note : null;
  return (
    <table className="w-full text-13">
      <caption className="pb-2 text-left text-12 text-ink-3">
        Solve time (this machine).{note ? ` ${note}` : ""}
      </caption>
      <thead>
        <tr>
          <th scope="col" className={cx(TH, "text-left")}>
            Run
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Median
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            p90
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Max
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Solves
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={5} className={cx(TD, "text-ink-2")}>
              The file has no timings.
            </td>
          </tr>
        ) : (
          rows.map(({ name, t }) => (
            <tr key={name}>
              <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
                {name}
              </th>
              <td className={cx(TD, "num text-right text-ink")}>{t.n > 0 ? formatSeconds(t.median_s) : "none"}</td>
              <td className={cx(TD, "num text-right text-ink-2")}>
                {t.p90_s !== undefined && t.n > 0 ? formatSeconds(t.p90_s) : "not reported"}
              </td>
              <td className={cx(TD, "num text-right text-ink-2")}>{t.n > 0 ? formatSeconds(t.max_s) : "none"}</td>
              <td className={cx(TD, "num text-right text-ink-2")}>{formatNumber(t.n)}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

export function CanonicalTable({ data }: { data: CanonicalResults }): ReactElement {
  return (
    <table className="w-full text-13">
      <caption className="pb-2 text-left text-12 text-ink-3">
        Canonical run <span className="num">{data.scenario_id}</span>, seed <span className="num">{data.seed}</span>,
        mean of <span className="num">{data.draws}</span> realized days.
      </caption>
      <thead>
        <tr>
          <th scope="col" className={cx(TH, "text-left")}>
            Arm
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Spoiled
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Demand filled
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Net
          </th>
          <th scope="col" className={cx(TH, "text-right")}>
            Validator
          </th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(data.arms).map(([arm, a]) => (
          <tr key={arm}>
            <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
              {armName(arm)}
            </th>
            <td className={cx(TD, "num text-right text-ink")}>{formatKg(a.outcome.spoiled_kg)}</td>
            <td className={cx(TD, "num text-right text-ink")}>{formatPct(a.outcome.demand_filled_pct)}</td>
            <td className={cx(TD, "num text-right text-ink")}>{formatInr(a.outcome.net_inr)}</td>
            <td className={cx(TD, "text-right")}>
              <Tag tone={a.validation.status === "PASS" ? "good" : "bad"}>
                {a.validation.status === "PASS" ? "pass" : `${formatNumber(a.validation.violation_count)} violations`}
              </Tag>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
