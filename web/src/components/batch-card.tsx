import { memo, type ReactElement } from "react";

import type { ChangeKind } from "../api/types";
import type { CardModel } from "../lib/board";
import { cx } from "../lib/cx";
import { formatDiscount, formatHours, formatNumber } from "../lib/format";
import { RAMP_FILL, RAMP_WORD, rampStep } from "../lib/perishability";
import { LockIcon } from "./icons";

function describe(card: CardModel, horizonH: number, change: ChangeKind | undefined): string {
  const parts = [
    card.batchId,
    card.commodity,
    card.split ? `${formatNumber(card.kg)} of ${formatNumber(card.totalKg)} kg` : `${formatNumber(card.kg)} kg`,
  ];
  if (card.saleH !== null && card.shelfH !== null && card.marginH !== null) {
    parts.push(
      `on sale at ${formatHours(card.saleH)}, shelf life ends at ${formatHours(card.shelfH)}, ${formatHours(card.marginH)} margin`,
    );
  }
  if (card.marginH !== null) parts.push(RAMP_WORD[rampStep(card.marginH, horizonH)]);
  if (card.discount > 0) parts.push(formatDiscount(card.discount));
  if (card.dispatched) parts.push("already dispatched");
  else if (card.locked) parts.push("locked by dispatcher");
  if (change) parts.push(`changed in replan: ${change}`);
  return parts.join(", ");
}

export const BatchCard = memo(function BatchCard({
  card,
  horizonH,
  highlighted,
  change,
  onOpen,
  onHover,
}: {
  card: CardModel;
  horizonH: number;
  highlighted: boolean;
  change: ChangeKind | undefined;
  onOpen: (batchId: string, trigger: HTMLElement) => void;
  onHover: (batchId: string | null) => void;
}): ReactElement {
  const step = card.marginH === null ? null : rampStep(card.marginH, horizonH);
  const usedPct = card.saleH !== null && card.shelfH ? Math.min(100, Math.max(0, (card.saleH / card.shelfH) * 100)) : 0;

  return (
    <button
      type="button"
      data-flip-key={card.key}
      data-batch-trigger=""
      onClick={(event) => {
        onOpen(card.batchId, event.currentTarget);
      }}
      onMouseEnter={() => {
        onHover(card.batchId);
      }}
      onMouseLeave={() => {
        onHover(null);
      }}
      className={cx(
        "relative block w-full overflow-hidden rounded-sm border bg-raised px-2 pb-1 pt-1 text-left transition-colors duration-fast",
        highlighted ? "border-ink bg-highlight" : "border-line hover:border-line-strong",
        change && "card-changed",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-12 text-ink">
          <span className="num font-medium">{card.batchId}</span>
          <span className="text-ink-3"> · </span>
          <span className="num">{formatNumber(card.kg)}</span>
          {card.split ? (
            <>
              <span className="text-ink-3"> of </span>
              <span className="num">{formatNumber(card.totalKg)}</span>
            </>
          ) : null}
          <span className="text-ink-2"> kg</span>
        </span>
        {card.discount > 0 ? (
          <span className="inline-flex h-4 shrink-0 items-center rounded-sm border border-line-strong px-1 text-12 leading-none text-ink">
            <span className="num">{Math.round(card.discount * 100)}%</span>&nbsp;off
          </span>
        ) : null}
      </span>
      <span className="mt-0.5 flex items-center justify-between gap-2 text-12">
        <span className="flex min-w-0 items-center gap-1 text-ink-2">
          <span className="truncate">{card.commodity}</span>
          {card.locked ? <LockIcon size={12} className="shrink-0 text-ink" /> : null}
        </span>
        {card.saleH !== null && card.shelfH !== null && card.marginH !== null ? (
          <span className="flex shrink-0 items-center gap-2">
            <span className="text-ink-3">
              <span className="num">{formatHours(card.saleH)}</span> →{" "}
              <span className="num">{formatHours(card.shelfH)}</span>
            </span>
            <span className="num font-medium text-ink">+{formatHours(card.marginH)}</span>
          </span>
        ) : null}
      </span>
      <span className="sr-only">. {describe(card, horizonH, change)}</span>
      {step !== null ? (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 flex h-0.5 bg-sunken">
          <span className="h-full bg-line-strong" style={{ width: `${usedPct}%` }} />
          <span className={cx("h-full flex-1", RAMP_FILL[step])} />
        </span>
      ) : null}
    </button>
  );
});
