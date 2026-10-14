import type { ReactElement } from "react";

import { getConfig } from "../api/client";
import type { PlanResponse, ScenarioInfo } from "../api/types";
import { cx } from "../lib/cx";
import { formatInr, formatInrDelta, formatKg, formatKgDelta, formatNumber, formatPct, formatPp } from "../lib/format";
import { useResource } from "../lib/use-resource";
import { AlertIcon, CheckIcon } from "./icons";
import { NumText, PanelTitle, Swatch, Tip } from "./primitives";

type Better = "lower" | "higher";

interface MetricRow {
  label: string;
  lading: number;
  fefo: number;
  format: (v: number) => string;
  formatDelta: (v: number) => string;
  better: Better;
  epsilon: number;
}

function verdict(delta: number, better: Better, epsilon: number): "better" | "worse" | "same" {
  if (Math.abs(delta) < epsilon) return "same";
  const good = better === "lower" ? delta < 0 : delta > 0;
  return good ? "better" : "worse";
}

function Metric({ row }: { row: MetricRow }): ReactElement {
  const delta = row.lading - row.fefo;
  const call = verdict(delta, row.better, row.epsilon);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_96px_96px] items-baseline gap-x-2 border-t border-line py-2">
      <dt className="text-12 text-ink-2">{row.label}</dt>
      <dd className="num text-right text-14 font-medium text-ink">{row.format(row.lading)}</dd>
      <dd className="num text-right text-14 text-ink-2">{row.format(row.fefo)}</dd>
      <dd className="col-span-3 mt-0.5 flex items-baseline justify-end gap-2 text-12">
        <span className="text-ink-3">Lading − FEFO</span>
        <span
          className={cx(
            "num font-medium",
            call === "better" && "text-good",
            call === "worse" && "text-bad",
            call === "same" && "text-ink-2",
          )}
        >
          {row.formatDelta(delta)}
        </span>
        <span
          className={cx(
            "w-10 text-right",
            call === "better" ? "text-good" : call === "worse" ? "text-bad" : "text-ink-3",
          )}
        >
          {call}
        </span>
      </dd>
    </div>
  );
}

function SolverTimeoutNote({ gap }: { gap: number | null }): ReactElement {
  const [config] = useResource("config", getConfig);
  const budget = config.status === "ready" ? config.data.planner.live_time_limit_s : undefined;
  return (
    <p
      role="status"
      className="mt-2 flex items-start gap-2 rounded-sm border border-warn bg-warn-wash p-2 text-12 text-warn"
    >
      <AlertIcon size={14} className="mt-0.5 shrink-0" />
      <span>
        Planner hit its {budget !== undefined ? <span className="num">{budget} s</span> : "time"} budget · best plan
        found
        {gap !== null ? (
          <>
            , optimality gap <span className="num">{formatPct(gap * 100, 2)}</span>
          </>
        ) : null}
      </span>
    </p>
  );
}

function ValidatorRow({ response }: { response: PlanResponse }): ReactElement {
  const validation = response.lading.validation;
  const checks = Object.values(validation.checks).reduce((sum, n) => sum + n, 0);
  const rules = Object.keys(validation.checks).length;
  const first = validation.violations[0];
  if (validation.status === "PASS") {
    return (
      <Tip
        content={
          <>
            The validator re-derives every total from the plan and scenario on its own:{" "}
            <span className="num">{formatNumber(checks)}</span> checks across <span className="num">{rules}</span>{" "}
            rules.
          </>
        }
      >
        <p tabIndex={0} className="mt-2 flex items-center gap-2 rounded-sm text-12 text-ink-2">
          <CheckIcon size={14} className="text-good" />
          <span>
            <span className="num">{validation.violation_count}</span> violations · independently checked
          </span>
        </p>
      </Tip>
    );
  }
  return (
    <div
      role="alert"
      className="mt-2 flex items-start gap-2 rounded-sm border border-bad bg-bad-wash p-2 text-12 text-ink"
    >
      <AlertIcon size={14} className="mt-0.5 shrink-0 text-bad" />
      <div>
        <p className="font-semibold">
          <span className="num">{validation.violation_count}</span> violations · the independent validator rejected this
          plan
        </p>
        {first ? (
          <p className="mt-0.5 text-ink-2">
            <NumText text={first.message} /> <span className="num text-ink-3">({first.ref})</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function OutcomeStrip({
  response,
  info,
  busy,
}: {
  response: PlanResponse | null;
  info: ScenarioInfo | undefined;
  busy: boolean;
}): ReactElement {
  const scenarioWord = info?.kind === "held-out" ? "held-out scenario" : "control scenario";
  const seed = response?.scenario.seed ?? info?.seed ?? null;
  const label = `executed against realized demand and delays · ${scenarioWord}${seed !== null ? ` · seed ${seed}` : ""}`;

  if (!response) {
    return (
      <section aria-labelledby="outcome-title" className="border-b border-line p-4">
        <PanelTitle id="outcome-title">Outcome</PanelTitle>
        <div className="mt-2 flex items-center gap-4 text-12 text-ink-3">
          <span className="flex items-center gap-1">
            <Swatch series="lading" /> Lading
          </span>
          <span className="flex items-center gap-1">
            <Swatch series="fefo" /> FEFO
          </span>
        </div>
        <p className="mt-3 text-13 text-ink-2">
          Run the plan to compare Lading with first-expiry-first-out dispatch on spoiled kg, demand filled and net ₹.
        </p>
        <p className="mt-2 text-12 text-ink-3">
          <NumText text={label} />
        </p>
      </section>
    );
  }

  const { lading, fefo } = response;
  const rows: MetricRow[] = [
    {
      label: "Spoiled",
      lading: lading.outcome.spoiled_kg,
      fefo: fefo.outcome.spoiled_kg,
      format: formatKg,
      formatDelta: formatKgDelta,
      better: "lower",
      epsilon: 0.5,
    },
    {
      label: "Demand filled",
      lading: lading.outcome.demand_filled_pct,
      fefo: fefo.outcome.demand_filled_pct,
      format: (v) => formatPct(v),
      formatDelta: (v) => formatPp(v),
      better: "higher",
      epsilon: 0.05,
    },
    {
      label: "Net",
      lading: lading.outcome.net_inr,
      fefo: fefo.outcome.net_inr,
      format: formatInr,
      formatDelta: formatInrDelta,
      better: "higher",
      epsilon: 0.5,
    },
  ];

  return (
    <section
      aria-labelledby="outcome-title"
      aria-busy={busy}
      className={cx("border-b border-line p-4 transition-opacity duration-slow", busy && "opacity-50")}
    >
      <PanelTitle
        id="outcome-title"
        aside={
          <span className="text-12 text-ink-3">
            mean of <span className="num">{formatNumber(lading.outcome.draws)}</span> realized days
          </span>
        }
      >
        Outcome
      </PanelTitle>
      <dl className="mt-2">
        <div className="grid grid-cols-[minmax(0,1fr)_96px_96px] gap-x-2 pb-1 text-12 text-ink-2">
          <dt className="sr-only">Series</dt>
          <dd className="col-start-2 flex items-center justify-end gap-1 font-medium text-ink">
            <Swatch series="lading" /> Lading
          </dd>
          <dd className="flex items-center justify-end gap-1">
            <Swatch series="fefo" /> FEFO
          </dd>
        </div>
        {rows.map((row) => (
          <Metric key={row.label} row={row} />
        ))}
      </dl>
      <p className="mt-1 text-12 text-ink-3">
        <NumText text={label} />
      </p>
      <ValidatorRow response={response} />
      {response.solver_state === "SOLVER_TIMEOUT" ? <SolverTimeoutNote gap={lading.plan.solver?.gap ?? null} /> : null}
    </section>
  );
}
