import type { ReactElement } from "react";

import type { DisruptionInfo } from "../api/types";
import { DISRUPTION_WORDS } from "../lib/codes";
import { cx } from "../lib/cx";
import { Button, Kbd, NumText, PanelTitle } from "./primitives";

function knownBefore(disruptions: DisruptionInfo[], slotLabels: Map<number, string>): string | null {
  const slots = new Set(disruptions.map((d) => d.at_slot));
  if (slots.size !== 1) return null;
  const [only] = [...slots];
  return only === undefined ? null : (slotLabels.get(only) ?? null);
}

export function DisruptPanel({
  disruptions,
  slotLabels,
  active,
  pending,
  canReset,
  onDisrupt,
  onReset,
}: {
  disruptions: DisruptionInfo[];
  slotLabels: Map<number, string>;
  active: number | null;
  pending: number | null;
  canReset: boolean;
  onDisrupt: (index: number) => void;
  onReset: () => void;
}): ReactElement {
  const shared = knownBefore(disruptions, slotLabels);
  return (
    <section aria-labelledby="disrupt-title" className="border-b border-line px-4 py-3">
      <PanelTitle
        id="disrupt-title"
        aside={
          <Button size="sm" variant="ghost" onClick={onReset} disabled={!canReset}>
            Reset to base plan
          </Button>
        }
      >
        Disrupt
      </PanelTitle>
      <p className="mt-0.5 text-12 text-ink-3">
        Each replan is the base plan plus one disruption
        {shared ? (
          <>
            , known before <span className="num">{shared}</span>
          </>
        ) : null}
        .
      </p>
      {disruptions.length === 0 ? (
        <p className="mt-3 text-12 text-ink-2">This scenario has no curated disruptions.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1">
          {disruptions.map((d) => {
            const isActive = active === d.index;
            const isPending = pending === d.index;
            const ownSlot = shared ? null : slotLabels.get(d.at_slot);
            return (
              <li key={d.index}>
                <button
                  type="button"
                  aria-pressed={isActive}
                  aria-keyshortcuts={String(d.index + 1)}
                  onClick={() => {
                    onDisrupt(d.index);
                  }}
                  className={cx(
                    "flex w-full items-start gap-2 rounded border px-2 py-2 text-left transition-colors duration-fast",
                    isActive
                      ? "border-ink bg-highlight"
                      : "border-line bg-raised hover:border-line-strong hover:bg-highlight",
                  )}
                >
                  <Kbd className="mt-px">{d.index + 1}</Kbd>
                  <span className="min-w-0 flex-1 text-13 text-ink">
                    <NumText text={d.label} />
                    <span className="sr-only">, {DISRUPTION_WORDS[d.kind].toLowerCase()}</span>
                    {ownSlot ? (
                      <span className="block text-12 text-ink-3">
                        known before <span className="num">{ownSlot}</span>
                      </span>
                    ) : null}
                  </span>
                  {isPending || isActive ? (
                    <span className="shrink-0 text-12 text-ink-2">{isPending ? "re-planning" : "applied"}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
