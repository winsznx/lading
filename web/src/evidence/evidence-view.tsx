import { type ReactElement, useCallback } from "react";

import { getAssumptions, getResult } from "../api/client";
import type { ManifestResults, ResultFiles, ResultName } from "../api/types";
import { isNotFound } from "../lib/errors";
import { formatNumber } from "../lib/format";
import { useResource, type Resource } from "../lib/use-resource";
import { AssumptionsTable } from "./assumptions";
import { HeldoutSection } from "./heldout-section";
import { SensitivityChart } from "./sensitivity-chart";
import { CopyCommand, FileState, KeyValue, Section } from "./shared";
import {
  AblationTable,
  CanonicalTable,
  ControlsList,
  StressTable,
  TimingsTable,
  ValidatorTable,
  VerdictPanel,
} from "./tables";

const REPRODUCE = "make reproduce";

const NAV = [
  ["verdict", "Verdict"],
  ["heldout", "Held-out"],
  ["sensitivity", "Elasticity"],
  ["ablations", "Ablations"],
  ["stress", "Stress"],
  ["validator", "Validator"],
  ["assumptions", "Assumptions"],
  ["manifest", "Manifest"],
  ["reproduce", "Reproduce"],
] as const;

function useResult<K extends ResultName>(name: K): [Resource<ResultFiles[K]>, () => void] {
  const load = useCallback((signal: AbortSignal) => getResult(name, signal), [name]);
  return useResource(`result:${name}`, load);
}

const MANIFEST_KNOWN = new Set([
  "commit",
  "dirty",
  "solver",
  "cost_model_sha256",
  "planner_config_sha256",
  "python",
  "libraries",
  "host",
  "seeds",
  "draws_per_scenario",
]);

function seedRange(seeds: unknown[]): string {
  const nums = seeds.filter((s): s is number => typeof s === "number");
  if (nums.length !== seeds.length || nums.length < 3) return seeds.map(String).join(", ");
  const contiguous = nums.every((n, i) => i === 0 || n === (nums[i - 1] ?? n) + 1);
  return contiguous ? `${nums[0] ?? ""}–${nums[nums.length - 1] ?? ""} (${nums.length} seeds)` : nums.join(", ");
}

function Plain({ value }: { value: unknown }): ReactElement {
  if (Array.isArray(value)) return <span className="num text-12">{seedRange(value)}</span>;
  if (typeof value === "object" && value !== null) {
    return (
      <ul className="flex flex-col gap-1 [&_ul]:mt-1 [&_ul]:pl-4">
        {Object.entries(value as Record<string, unknown>).map(([key, inner]) => (
          <li key={key}>
            <span className="text-ink-2">{key.replace(/_/g, " ")}: </span>
            <Plain value={inner} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "boolean") return <span>{value ? "yes" : "no"}</span>;
  return <span className="num break-all">{String(value)}</span>;
}

function Manifest({ data }: { data: ManifestResults }): ReactElement {
  const libraries = Object.entries(data.libraries);
  const { name: solverName, version: solverVersion, ...solverSettings } = data.solver;
  const extra = Object.entries(data).filter(([key]) => !MANIFEST_KNOWN.has(key));
  return (
    <KeyValue
      rows={[
        {
          label: "Commit",
          value: (
            <span className="num break-all">
              {data.commit}
              {data.dirty ? (
                <span className="text-bad"> (uncommitted changes)</span>
              ) : (
                <span className="text-ink-3"> (clean)</span>
              )}
            </span>
          ),
        },
        {
          label: "Solver",
          value: (
            <>
              {solverName} <span className="num">{solverVersion}</span>
              {Object.keys(solverSettings).length > 0 ? (
                <span className="ml-3 text-12 text-ink-3">
                  {Object.entries(solverSettings).map(([key, v]) => (
                    <span key={key} className="mr-3">
                      {key.replace(/_/g, " ")} <span className="num">{String(v)}</span>
                    </span>
                  ))}
                </span>
              ) : null}
            </>
          ),
        },
        { label: "Cost model SHA-256", value: <span className="num break-all text-12">{data.cost_model_sha256}</span> },
        {
          label: "Planner config SHA-256",
          value: <span className="num break-all text-12">{data.planner_config_sha256}</span>,
        },
        { label: "Python", value: <span className="num">{data.python}</span> },
        {
          label: "Libraries",
          value:
            libraries.length === 0 ? (
              <span className="text-ink-3">none listed</span>
            ) : (
              <ul className="flex flex-wrap gap-x-4 gap-y-1">
                {libraries.map(([name, version]) => (
                  <li key={name}>
                    {name} <span className="num text-ink-2">{version}</span>
                  </li>
                ))}
              </ul>
            ),
        },
        { label: "Host", value: <span className="num break-all">{data.host}</span> },
        { label: "Seeds", value: <Plain value={data.seeds} /> },
        {
          label: "Realized days per scenario",
          value: <span className="num">{formatNumber(data.draws_per_scenario)}</span>,
        },
        ...extra.map(([key, value]) => ({
          label: key
            .replace(/_/g, " ")
            .replace(/sha256/i, "SHA-256")
            .replace(/^./, (c) => c.toUpperCase()),
          value: <Plain value={value} />,
        })),
      ]}
    />
  );
}

export function EvidenceView(): ReactElement {
  const [heldout, reloadHeldout] = useResult("heldout");
  const [ablations, reloadAblations] = useResult("ablations");
  const [stress, reloadStress] = useResult("stress");
  const [sensitivity, reloadSensitivity] = useResult("sensitivity");
  const [controls, reloadControls] = useResult("controls");
  const [verdict, reloadVerdict] = useResult("verdict");
  const [manifest, reloadManifest] = useResult("manifest");
  const [timings, reloadTimings] = useResult("timings");
  const [canonical, reloadCanonical] = useResult("canonical");
  const [assumptions, reloadAssumptions] = useResource("assumptions", getAssumptions);

  const results: Resource<unknown>[] = [
    heldout,
    ablations,
    stress,
    sensitivity,
    controls,
    verdict,
    manifest,
    timings,
    canonical,
  ];
  const nothingYet = results.every((r) => r.status === "error" && isNotFound(r.error));

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 pb-16 pt-6 lg:px-6">
      <div className="grid gap-8 lg:grid-cols-[168px_minmax(0,1fr)]">
        <nav aria-label="Evidence sections" className="hidden lg:block">
          <ul className="sticky top-6 flex flex-col gap-px text-13">
            {NAV.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="block rounded-sm px-2 py-1 text-ink-2 hover:bg-highlight hover:text-ink">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex min-w-0 flex-col gap-8">
          <header>
            <h1 className="text-20 font-semibold text-ink">Evidence</h1>
            <p className="mt-1 max-w-[72ch] text-13 text-ink-2">
              Every number on this page is read from the results files that <code className="num">{REPRODUCE}</code>{" "}
              writes, served by the planner API.
            </p>
          </header>

          {nothingYet ? (
            <div className="rounded-md border border-dashed border-line-strong bg-surface p-6">
              <p className="text-16 font-semibold text-ink">Evidence not generated yet. Run make reproduce.</p>
              <p className="mt-1 max-w-[64ch] text-13 text-ink-2">
                The planner API has no results files. Running the harness plans the held-out, ablation, stress and
                sensitivity scenarios, executes every arm, validates every plan and writes the files this page reads.
              </p>
              <div className="mt-4 max-w-[480px]">
                <CopyCommand command={REPRODUCE} />
              </div>
            </div>
          ) : (
            <>
              <Section id="verdict" title="Verdict" file="verdict.json">
                <FileState resource={verdict} file="results/verdict.json" onRetry={reloadVerdict}>
                  {(data) => <VerdictPanel data={data} />}
                </FileState>
              </Section>

              <Section id="heldout" title="Held-out scenarios" file="heldout.json">
                <FileState resource={heldout} file="results/heldout.json" onRetry={reloadHeldout}>
                  {(data) => <HeldoutSection data={data} />}
                </FileState>
              </Section>

              <Section
                id="sensitivity"
                title="Elasticity sensitivity"
                file="sensitivity.json"
                lede="The planner prices on a disclosed demand elasticity. Here the realized elasticity is scaled away from it to see when the gain over FEFO holds."
              >
                <FileState resource={sensitivity} file="results/sensitivity.json" onRetry={reloadSensitivity}>
                  {(data) => <SensitivityChart data={data} />}
                </FileState>
              </Section>

              <Section id="ablations" title="Ablations" file="ablations.json">
                <FileState resource={ablations} file="results/ablations.json" onRetry={reloadAblations}>
                  {(data) => <AblationTable data={data} />}
                </FileState>
              </Section>

              <Section id="stress" title="Stress families" file="stress.json">
                <FileState resource={stress} file="results/stress.json" onRetry={reloadStress}>
                  {(data) => <StressTable data={data} />}
                </FileState>
              </Section>

              <Section id="validator" title="Validator and controls">
                <div className="grid gap-6 xl:grid-cols-2">
                  <div className="flex flex-col gap-6">
                    <FileState resource={heldout} file="results/heldout.json" onRetry={reloadHeldout}>
                      {(data) => <ValidatorTable data={data} />}
                    </FileState>
                    <FileState resource={timings} file="results/timings.json" onRetry={reloadTimings}>
                      {(data) => <TimingsTable data={data} />}
                    </FileState>
                  </div>
                  <div className="flex flex-col gap-6">
                    <div>
                      <h3 className="pb-2 text-12 text-ink-3">Control scenarios, each with a known right answer</h3>
                      <FileState resource={controls} file="results/controls.json" onRetry={reloadControls}>
                        {(data) => <ControlsList data={data} />}
                      </FileState>
                    </div>
                    <FileState resource={canonical} file="results/canonical.json" onRetry={reloadCanonical}>
                      {(data) => <CanonicalTable data={data} />}
                    </FileState>
                  </div>
                </div>
              </Section>
            </>
          )}

          <Section
            id="assumptions"
            title="Assumptions"
            lede="Every synthetic input the scenario generator draws from, disclosed to every arm."
          >
            <FileState resource={assumptions} file="GET /assumptions" onRetry={reloadAssumptions}>
              {(data) => <AssumptionsTable data={data} />}
            </FileState>
          </Section>

          {nothingYet ? null : (
            <Section id="manifest" title="Manifest" file="manifest.json">
              <FileState resource={manifest} file="results/manifest.json" onRetry={reloadManifest}>
                {(data) => <Manifest data={data} />}
              </FileState>
            </Section>
          )}

          <Section
            id="reproduce"
            title="Reproduce"
            lede="From a clean checkout, this rebuilds every results file on this page."
          >
            <div className="max-w-[480px]">
              <CopyCommand command={REPRODUCE} />
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
