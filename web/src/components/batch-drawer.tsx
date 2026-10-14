import * as Dialog from "@radix-ui/react-dialog";
import type { ReactElement, RefObject } from "react";

import type { Controls, Decision, Lock, PlanResponse, Veto } from "../api/types";
import { ALTERNATIVE_WORDS, HOLD_WORDS } from "../lib/codes";
import { cx } from "../lib/cx";
import { formatDiscount, formatHours, formatInr, formatInrDelta, formatKg, shortMarket } from "../lib/format";
import { CloseIcon, LockIcon } from "./icons";
import { Button, Kbd, NumText, Tag } from "./primitives";

function statusTag(decision: Decision, dispatched: boolean): ReactElement {
  if (dispatched) return <Tag tone="strong">Dispatched</Tag>;
  if (decision.status === "assigned")
    return <Tag tone="strong">{decision.locked ? "Assigned, locked" : "Assigned"}</Tag>;
  return <Tag>{decision.hold_code ? HOLD_WORDS[decision.hold_code] : "Held at hub"}</Tag>;
}

function Summary({ decision }: { decision: Decision }): ReactElement {
  return (
    <dl className="grid grid-cols-[112px_minmax(0,1fr)] gap-x-3 gap-y-2 text-13">
      <dt className="text-ink-3">Market</dt>
      <dd className="text-ink">{decision.market_name ?? "Held at hub"}</dd>
      <dt className="text-ink-3">{decision.legs.length > 1 ? "Departures" : "Departure"}</dt>
      <dd>
        {decision.legs.length === 0 ? (
          <span className="text-ink-2">None</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {decision.legs.map((leg) => (
              <li key={`${leg.slot_id}-${leg.kg}`}>
                <span className="num text-ink">{leg.slot_label}</span>
                <span className="text-ink-3"> · </span>
                <span className="num text-ink">{formatKg(leg.kg)}</span>
                <span className="block text-12 text-ink-2">
                  on sale at <span className="num">{formatHours(leg.sale_h)}</span>, margin{" "}
                  <span className="num font-medium text-ink">+{formatHours(leg.margin_h)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </dd>
      <dt className="text-ink-3">Discount</dt>
      <dd className="text-ink">
        {decision.discount ? <span className="num">{formatDiscount(decision.discount)}</span> : "None, list price"}
      </dd>
      <dt className="text-ink-3">Shelf life</dt>
      <dd className="text-ink">
        <span className="num">{formatHours(decision.plan_shelf_h)}</span>
        <span className="text-ink-3">
          {" "}
          planned on {decision.basis === "robust" ? "a conservative" : "the point"} estimate
          {Math.abs(decision.plan_shelf_h - decision.shelf_h) > 0.05 ? (
            <>
              {" "}
              (estimate <span className="num">{formatHours(decision.shelf_h)}</span>)
            </>
          ) : null}
        </span>
      </dd>
      <dt className="text-ink-3">Batch net</dt>
      <dd className="text-ink">
        <span className="num">{formatInr(decision.net_inr)}</span>
        <span className="text-ink-3"> plan estimate for this batch</span>
      </dd>
    </dl>
  );
}

function Alternatives({ decision, sentences }: { decision: Decision; sentences: string[] }): ReactElement {
  if (decision.alternatives.length === 0) {
    return <p className="text-13 text-ink-2">No other market buys this commodity.</p>;
  }
  return (
    <ol className="flex flex-col">
      {decision.alternatives.map((alt, i) => (
        <li key={`${alt.market_id ?? "hold"}-${alt.code}`} className="border-t border-line py-2 first:border-t-0">
          <div className="flex items-baseline justify-between gap-3">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="truncate text-13 font-medium text-ink">{alt.market_name}</span>
              {ALTERNATIVE_WORDS[alt.code] !== alt.market_name ? (
                <span className="shrink-0 text-12 text-ink-3">{ALTERNATIVE_WORDS[alt.code]}</span>
              ) : null}
            </span>
            {alt.delta_inr !== null ? (
              <span className="num shrink-0 text-13 text-ink" title="Chosen plan minus this alternative, net ₹">
                {formatInrDelta(alt.delta_inr)}
              </span>
            ) : null}
          </div>
          {sentences[i] ? (
            <p className="mt-0.5 text-12 text-ink-2">
              <NumText text={sentences[i]} />
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function BatchDrawer({
  batchId,
  response,
  controls,
  busy,
  returnFocus,
  onClose,
  onApply,
}: {
  batchId: string | null;
  response: PlanResponse | null;
  controls: Controls;
  busy: boolean;
  returnFocus: RefObject<HTMLElement | null>;
  onClose: () => void;
  onApply: (next: Controls) => void;
}): ReactElement {
  const decision = response?.decisions.find((d) => d.batch_id === batchId) ?? null;
  const reason = batchId ? response?.reasons[batchId] : undefined;
  const scenario = response?.scenario ?? null;
  const dispatched = Boolean(batchId && scenario?.controls.dispatched.some((d) => d.batch_id === batchId));
  const lock = controls.locks.find((l) => l.batch_id === batchId) ?? null;
  const vetoes = controls.vetoes.filter((v) => v.batch_id === batchId);
  const marketName = new Map((scenario?.markets ?? []).map((m) => [m.id, shortMarket(m.name)]));
  const slotLabel = new Map((scenario?.slots ?? []).map((s) => [s.id, s.label]));
  const firstLeg = decision?.legs[0];
  const assignedMarket = decision?.market_id ?? null;
  const canAct = decision !== null && decision.status === "assigned" && !dispatched && assignedMarket !== null;
  const lockedHere =
    lock !== null && firstLeg !== undefined && lock.market_id === assignedMarket && lock.slot_id === firstLeg.slot_id;

  function lockHere(): void {
    if (!decision || !assignedMarket || !firstLeg) return;
    const next: Lock = { batch_id: decision.batch_id, market_id: assignedMarket, slot_id: firstLeg.slot_id };
    onApply({
      locks: [...controls.locks.filter((l) => l.batch_id !== decision.batch_id), next],
      vetoes: controls.vetoes,
    });
  }

  function vetoMarket(): void {
    if (!decision || !assignedMarket) return;
    const next: Veto = { batch_id: decision.batch_id, market_id: assignedMarket };
    onApply({
      locks: controls.locks.filter((l) => !(l.batch_id === next.batch_id && l.market_id === next.market_id)),
      vetoes: [...controls.vetoes, next],
    });
  }

  return (
    <Dialog.Root
      open={batchId !== null}
      modal={false}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Content
          onInteractOutside={(event) => {
            const target = event.target;
            if (target instanceof Element && target.closest("[data-batch-trigger]")) event.preventDefault();
          }}
          onCloseAutoFocus={(event) => {
            if (returnFocus.current?.isConnected) {
              event.preventDefault();
              returnFocus.current.focus();
            }
          }}
          className="sheet fixed inset-y-0 right-0 z-40 flex w-full max-w-[460px] flex-col border-l border-line bg-surface shadow-overlay focus:outline-none"
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <Dialog.Title className="text-16 font-semibold text-ink">
                <span className="num">{batchId}</span>
                {decision ? <span className="font-medium"> · {decision.commodity_name}</span> : null}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-12 text-ink-2">
                {decision ? (
                  <>
                    <span className="num">{formatKg(decision.kg)}</span> from {decision.origin}
                  </>
                ) : (
                  "This batch isn't in the current plan."
                )}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="inline-flex h-8 shrink-0 items-center gap-2 rounded px-2 text-ink-2 hover:bg-highlight hover:text-ink"
              >
                <Kbd>Esc</Kbd>
                <span className="sr-only">close batch details</span>
                <CloseIcon />
              </button>
            </Dialog.Close>
          </div>

          {decision ? (
            <div
              className={cx(
                "scroll-quiet min-h-0 flex-1 overflow-y-auto px-4 py-4 transition-opacity duration-slow",
                busy && "opacity-50",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                {statusTag(decision, dispatched)}
                {busy ? <span className="text-12 text-ink-3">re-planning with your change…</span> : null}
              </div>
              {reason ? (
                <p className="mt-3 text-14 text-ink">
                  <NumText text={reason.headline} />
                </p>
              ) : null}
              <div className="mt-4">
                <Summary decision={decision} />
              </div>

              <h3 className="mt-6 flex items-baseline justify-between text-13 font-semibold text-ink">
                Rejected alternatives
                <span className="text-12 font-normal text-ink-3">Δ net, chosen − this</span>
              </h3>
              <div className="mt-1">
                <Alternatives decision={decision} sentences={reason?.alternatives ?? []} />
              </div>
            </div>
          ) : (
            <div className="flex-1 px-4 py-4 text-13 text-ink-2">Run the plan again to see this batch.</div>
          )}

          <div className="border-t border-line px-4 py-3">
            {dispatched ? (
              <p className="mb-2 text-12 text-ink-2">Already on the road, so it can&apos;t be locked or vetoed.</p>
            ) : decision && decision.status !== "assigned" ? (
              <p className="mb-2 text-12 text-ink-2">Held batches have no market to lock or veto.</p>
            ) : null}
            {lock || vetoes.length > 0 ? (
              <ul className="mb-2 flex flex-wrap gap-1 text-12">
                {lock ? (
                  <li className="inline-flex h-6 items-center gap-1 rounded-sm border border-line-strong pl-2 text-ink">
                    <LockIcon size={12} />
                    Locked to {marketName.get(lock.market_id) ?? lock.market_id},{" "}
                    <span className="num">{slotLabel.get(lock.slot_id) ?? lock.slot_id}</span>
                    <button
                      type="button"
                      aria-label={`Remove lock on ${lock.batch_id}`}
                      onClick={() => {
                        onApply({ locks: controls.locks.filter((l) => l !== lock), vetoes: controls.vetoes });
                      }}
                      className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-ink-3 hover:bg-highlight hover:text-ink"
                    >
                      <CloseIcon size={12} />
                    </button>
                  </li>
                ) : null}
                {vetoes.map((veto) => (
                  <li
                    key={veto.market_id}
                    className="inline-flex h-6 items-center gap-1 rounded-sm border border-line-strong pl-2 text-ink"
                  >
                    Vetoed {marketName.get(veto.market_id) ?? veto.market_id}
                    <button
                      type="button"
                      aria-label={`Remove veto on ${veto.batch_id} at ${marketName.get(veto.market_id) ?? veto.market_id}`}
                      onClick={() => {
                        onApply({ locks: controls.locks, vetoes: controls.vetoes.filter((v) => v !== veto) });
                      }}
                      className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-ink-3 hover:bg-highlight hover:text-ink"
                    >
                      <CloseIcon size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button onClick={lockHere} disabled={!canAct || lockedHere}>
                <LockIcon size={14} />
                {lockedHere ? "Locked here" : "Lock here"}
              </Button>
              <Button variant="danger" onClick={vetoMarket} disabled={!canAct}>
                Veto {assignedMarket ? (marketName.get(assignedMarket) ?? assignedMarket) : "market"}
              </Button>
            </div>
            {canAct && firstLeg ? (
              <p className="mt-2 text-12 text-ink-3">
                Lock keeps it on {marketName.get(assignedMarket) ?? assignedMarket} at{" "}
                <span className="num">{firstLeg.slot_label}</span>. Veto forbids that market for this batch. Either one
                re-plans now.
              </p>
            ) : null}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
