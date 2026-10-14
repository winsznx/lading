import * as Tabs from "@radix-ui/react-tabs";
import {
  lazy,
  type ReactElement,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getScenario } from "../api/client";
import type { ChangeKind, Controls, Lock, PlanResponse, ReplanResponse, ScenarioInfo, Veto } from "../api/types";
import { buildBoard } from "../lib/board";
import { DISRUPTION_WORDS } from "../lib/codes";
import { formatKg, formatSeconds, plural } from "../lib/format";
import { useFlip, type Flip } from "../lib/use-flip";
import { useHotkeys } from "../lib/use-hotkeys";
import { useResource } from "../lib/use-resource";
import { usePlanner } from "../state/use-planner";
import { BatchDrawer } from "./batch-drawer";
import { ChangesPanel } from "./changes-panel";
import { ControlsBar } from "./controls-bar";
import { DisruptPanel } from "./disrupt-panel";
import { ErrorBoundary } from "./error-boundary";
import { InventoryRail } from "./inventory-rail";
import { OutcomeStrip } from "./outcome-strip";
import { PlanBoard } from "./plan-board";
import { Button, ErrorNotice, Kbd, NumText } from "./primitives";
import { ScenarioPicker } from "./scenario-picker";
import { SolveChip } from "./solve-chip";
import { TopBar } from "./top-bar";
import { Trays } from "./trays";

const EvidenceView = lazy(() => import("../evidence/evidence-view").then((m) => ({ default: m.EvidenceView })));

type View = "plan" | "evidence";

function isReplan(response: PlanResponse | null): response is ReplanResponse {
  return response !== null && "changes" in response;
}

export function Console({
  scenarios,
  scenarioId,
  onSelectScenario,
}: {
  scenarios: ScenarioInfo[];
  scenarioId: string;
  onSelectScenario: (id: string) => void;
}): ReactElement {
  const info = scenarios.find((s) => s.id === scenarioId);
  const [view, setView] = useState<View>("plan");
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const loadScenario = useCallback((signal: AbortSignal) => getScenario(scenarioId, signal), [scenarioId]);
  const [detail, reloadDetail] = useResource(`scenario:${scenarioId}`, loadScenario);

  const flipRef = useRef<Flip | null>(null);
  const beforeCommit = useCallback(() => {
    flipRef.current?.capture();
  }, []);
  const planner = usePlanner(scenarioId, beforeCommit);
  const flip = useFlip(planner.state.seq);
  useLayoutEffect(() => {
    flipRef.current = flip;
  });

  const { current, solving, failure, diffOpen, lastElapsed } = planner.state;
  const response = current?.response ?? null;
  const scenario = response?.scenario ?? (detail.status === "ready" ? detail.data : null);
  const board = useMemo(() => (scenario ? buildBoard(scenario, response) : null), [scenario, response]);
  const replanResponse = isReplan(response) ? response : null;
  const changes = useMemo<Map<string, ChangeKind> | null>(
    () => (replanResponse && diffOpen ? new Map(replanResponse.changes.map((c) => [c.batch_id, c.kind])) : null),
    [replanResponse, diffOpen],
  );
  const slotLabels = useMemo(() => new Map((scenario?.slots ?? []).map((s) => [s.index, s.label])), [scenario]);
  const busy = solving !== null;
  const ready = scenario !== null;

  const changesRef = useRef<HTMLDivElement>(null);
  const landedSeq = current?.seq ?? 0;
  const landedReplan = current?.kind === "replan";
  useEffect(() => {
    if (!landedReplan) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    changesRef.current?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [landedSeq, landedReplan]);

  const openBatch = useCallback((batchId: string, trigger: HTMLElement) => {
    returnFocus.current = trigger;
    setDrawerId(batchId);
  }, []);
  const closeDrawer = useCallback(() => {
    setDrawerId(null);
  }, []);

  function toggleView(): void {
    setDrawerId(null);
    setView((v) => (v === "plan" ? "evidence" : "plan"));
  }

  useHotkeys((key) => {
    if (key === "e" || key === "E") {
      toggleView();
      return;
    }
    if (view !== "plan" || !ready) return;
    if (key === "r" || key === "R") {
      planner.runPlan();
      return;
    }
    if (/^[1-4]$/.test(key)) {
      const index = Number(key) - 1;
      if (info?.disruptions.some((d) => d.index === index)) planner.runDisruption(index);
    }
  });

  const { applyControls, controls } = planner;
  const removeLock = useCallback(
    (lock: Lock) => {
      applyControls({ locks: controls.locks.filter((l) => l !== lock), vetoes: controls.vetoes });
    },
    [applyControls, controls],
  );
  const removeVeto = useCallback(
    (veto: Veto) => {
      applyControls({ locks: controls.locks, vetoes: controls.vetoes.filter((v) => v !== veto) });
    },
    [applyControls, controls],
  );
  const apply = useCallback(
    (next: Controls) => {
      applyControls(next);
    },
    [applyControls],
  );

  const expectedS = solving
    ? (lastElapsed[solving.kind] ?? (solving.kind === "plan" ? (info?.expected_solve_s ?? null) : null))
    : null;
  const last = current ? { kind: current.kind, elapsedS: current.response.elapsed_s } : null;

  const activeDisruption = planner.activeDisruption;
  const disruptionInfo = info?.disruptions.find((d) => d.index === activeDisruption);
  const status = solving
    ? solving.kind === "plan"
      ? "Planning"
      : "Re-planning"
    : current
      ? current.kind === "replan" && disruptionInfo
        ? `Replan: ${DISRUPTION_WORDS[disruptionInfo.kind].toLowerCase()}`
        : "Base plan"
      : "No plan yet";

  let overlay: ReactElement | null = null;
  if (!current && scenario) {
    if (failure) {
      overlay = <ErrorNotice error={failure.error} onRetry={planner.retry} />;
    } else if (solving) {
      overlay = (
        <div role="status" className="rounded border border-line bg-raised p-4 text-13 text-ink">
          <p className="font-medium">
            {solving.kind === "plan" ? "Planning" : "Re-planning"} {plural(scenario.batches.length, "batch", "batches")}{" "}
            across {plural(scenario.markets.length, "market")} and {plural(scenario.slots.length, "departure")}
          </p>
          <p className="mt-1 text-12 text-ink-2">
            {expectedS !== null ? (
              <>
                Expected in about <span className="num">{formatSeconds(expectedS)}</span>. The planner solves the plan,
                FEFO runs on the same stock, and both are executed against realized days.
              </>
            ) : (
              "Measuring how long this scenario takes. The planner solves the plan, FEFO runs on the same stock, and both are executed against realized days."
            )}
          </p>
        </div>
      );
    } else {
      overlay = (
        <div className="rounded border border-line bg-raised p-4">
          <p className="text-14 font-medium text-ink">No plan yet</p>
          <p className="mt-1 text-13 text-ink-2">
            Run the plan to place {plural(scenario.batches.length, "batch", "batches")} (
            <span className="num">{formatKg(scenario.batches.reduce((s, b) => s + b.kg, 0))}</span>) across{" "}
            {plural(scenario.markets.length, "market")} and {plural(scenario.slots.length, "departure")}.
          </p>
          <Button variant="primary" className="mt-3" onClick={planner.runPlan}>
            Run plan <Kbd inverse>R</Kbd>
          </Button>
        </div>
      );
    }
  }

  const topControls = (
    <>
      <ScenarioPicker scenarios={scenarios} selectedId={scenarioId} onSelect={onSelectScenario} />
      <Button variant="primary" onClick={planner.runPlan} disabled={!ready} aria-keyshortcuts="R">
        Run plan <Kbd inverse>R</Kbd>
      </Button>
      <SolveChip solving={solving?.kind ?? null} expectedS={expectedS} last={last} />
    </>
  );

  const meta = scenario ? (
    <p className="flex flex-wrap gap-x-3 text-12 text-ink-3">
      <span>{scenario.hub.name}</span>
      <span>{plural(scenario.batches.length, "batch", "batches")}</span>
      <span className="num">{formatKg(scenario.batches.reduce((s, b) => s + b.kg, 0))}</span>
      <span>{plural(scenario.markets.length, "market")}</span>
      <span>{plural(scenario.trucks.length, "truck")}</span>
      <span>{scenario.synthetic ? "synthetic data" : "organizer data"}</span>
    </p>
  ) : null;

  return (
    <Tabs.Root
      value={view}
      onValueChange={(value) => {
        setDrawerId(null);
        setView(value === "evidence" ? "evidence" : "plan");
      }}
      className="flex min-h-dvh flex-col lg:h-dvh"
    >
      <TopBar controls={topControls} meta={meta} />

      <main className="flex min-h-0 flex-1 flex-col">
        <Tabs.Content value="plan" className="console-grid min-h-0 flex-1 focus-visible:outline-none">
          <div
            tabIndex={0}
            className="area-rail scroll-quiet min-h-0 border-line bg-surface lg:overflow-y-auto lg:border-r"
          >
            {scenario ? (
              <InventoryRail
                scenario={scenario}
                hoveredId={hoveredId}
                interactive={current !== null}
                onHover={setHoveredId}
                onOpen={openBatch}
              />
            ) : detail.status === "error" ? (
              <div className="p-3">
                <ErrorNotice error={detail.error} onRetry={reloadDetail} compact />
              </div>
            ) : (
              <p role="status" className="p-3 text-12 text-ink-3">
                Loading inventory for {info?.label ?? scenarioId}…
              </p>
            )}
          </div>

          <section aria-label="Plan" className="area-plan flex min-h-0 min-w-0 flex-col bg-paper">
            <h1 className="sr-only">Dispatch plan for {info?.label ?? scenarioId}</h1>
            {scenario && board ? (
              <>
                <ControlsBar
                  scenario={scenario}
                  controls={controls}
                  status={status}
                  onRemoveLock={removeLock}
                  onRemoveVeto={removeVeto}
                />
                {failure && current ? (
                  <div className="border-b border-line p-3">
                    <ErrorNotice
                      error={failure.error}
                      onRetry={planner.retry}
                      onDismiss={planner.dismissFailure}
                      footnote="The board still shows the last plan that solved, from before this change."
                      compact
                    />
                  </div>
                ) : null}
                <ErrorBoundary what="the plan board">
                  <PlanBoard
                    board={board}
                    horizonH={scenario.policy.horizon_h}
                    hoveredId={hoveredId}
                    changes={changes}
                    busy={busy}
                    containerRef={flip.containerRef}
                    overlay={overlay}
                    onOpen={openBatch}
                    onHover={setHoveredId}
                  />
                  {current ? <Trays held={board.held} infeasible={board.infeasible} onOpen={openBatch} /> : null}
                </ErrorBoundary>
                <section aria-label="Cause and effect" className="shrink-0 border-t border-line bg-surface px-3 py-2">
                  <p className="flex min-h-5 gap-2 text-13 text-ink">
                    <span className="shrink-0 text-12 leading-5 text-ink-3">
                      {current?.kind === "replan" ? "Disruption effect" : "Plan effect"}
                    </span>
                    {response ? (
                      <NumText text={response.effect} className={busy ? "text-ink-3" : undefined} />
                    ) : (
                      <span className="text-ink-3">Appears after the first plan.</span>
                    )}
                  </p>
                </section>
              </>
            ) : detail.status === "error" ? (
              <div className="p-4">
                <ErrorNotice error={detail.error} onRetry={reloadDetail} />
              </div>
            ) : (
              <p role="status" className="p-4 text-13 text-ink-3">
                Loading the plan board for {info?.label ?? scenarioId}…
              </p>
            )}
          </section>

          <div className="area-outcome min-w-0 border-line bg-surface lg:border-l">
            <OutcomeStrip response={response} info={info} busy={busy} />
          </div>

          <section
            aria-label="Disruptions and changes"
            className="area-ops scroll-quiet min-h-0 min-w-0 border-line bg-surface lg:overflow-y-auto lg:border-l"
          >
            <DisruptPanel
              disruptions={info?.disruptions ?? []}
              slotLabels={slotLabels}
              active={current?.kind === "replan" ? current.disruptionIndex : null}
              pending={solving?.kind === "replan" ? solving.disruptionIndex : null}
              canReset={current?.kind === "replan" || solving?.kind === "replan"}
              onDisrupt={planner.runDisruption}
              onReset={planner.resetToBase}
            />
            <div ref={changesRef}>
              {replanResponse ? (
                <ChangesPanel
                  response={replanResponse}
                  open={diffOpen}
                  busy={busy}
                  onDismiss={planner.dismissDiff}
                  onReopen={planner.reopenDiff}
                  onOpenBatch={openBatch}
                />
              ) : (
                <p className="p-4 text-12 text-ink-3">
                  After a disruption, the batches that changed are listed here with the reason for each.
                </p>
              )}
            </div>
          </section>
        </Tabs.Content>

        <Tabs.Content value="evidence" className="min-h-0 flex-1 overflow-y-auto focus-visible:outline-none">
          <ErrorBoundary what="the evidence view">
            <Suspense fallback={<p className="p-6 text-13 text-ink-3">Loading the evidence view…</p>}>
              <EvidenceView />
            </Suspense>
          </ErrorBoundary>
        </Tabs.Content>
      </main>

      <BatchDrawer
        batchId={view === "plan" ? drawerId : null}
        response={response}
        controls={controls}
        busy={busy}
        returnFocus={returnFocus}
        onClose={closeDrawer}
        onApply={apply}
      />
    </Tabs.Root>
  );
}
