import type { ReactElement, ReactNode, RefObject } from "react";

import type { ChangeKind, Market } from "../api/types";
import type { BoardModel, ColumnModel } from "../lib/board";
import { cx } from "../lib/cx";
import { formatHours, formatKg, formatNumber, formatPct, shortMarket } from "../lib/format";
import { BatchCard } from "./batch-card";
import { Tip } from "./primitives";

const MARKET_COL = "minmax(104px, 120px)";
const COLLAPSED_COL = "44px";
const OPEN_COL = "minmax(232px, 1fr)";
const EMPTY_COL = "minmax(96px, 1fr)";

function columnTrack(column: ColumnModel, hasPlan: boolean): string {
  if (!hasPlan) return EMPTY_COL;
  return column.collapsed ? COLLAPSED_COL : OPEN_COL;
}

function CapacityBar({ column }: { column: ColumnModel }): ReactElement {
  const share = column.capacityKg > 0 ? Math.min(1, column.loadKg / column.capacityKg) : 0;
  return (
    <span aria-hidden="true" className="block h-0.5 w-full overflow-hidden rounded-sm bg-sunken">
      <span className="block h-full bg-ink-2" style={{ width: `${share * 100}%` }} />
    </span>
  );
}

function capacityText(column: ColumnModel): string {
  if (column.capacityKg === 0) return `${column.slot.label}: no truck available`;
  return `${column.slot.label}: ${formatKg(column.loadKg)} of ${formatKg(column.capacityKg)} loaded on ${column.trucksUsed} of ${column.trucksAvailable} trucks`;
}

function ColumnHeader({ column, hasPlan }: { column: ColumnModel; hasPlan: boolean }): ReactElement {
  const [day, time] = column.slot.label.split(" ");
  const share = column.capacityKg > 0 ? (column.loadKg / column.capacityKg) * 100 : 0;
  const collapsed = hasPlan && column.collapsed;
  return (
    <div role="columnheader" className="sticky top-0 z-20 border-b border-l border-line bg-surface px-2 pb-2 pt-2">
      <Tip content={capacityText(column)} side="bottom">
        <button type="button" className="flex w-full flex-col gap-1 rounded-sm text-left">
          {collapsed ? (
            <span className="num flex flex-col text-12 leading-4 text-ink-3">
              <span>{day}</span>
              <span>{time}</span>
            </span>
          ) : (
            <span className="flex items-baseline justify-between gap-2">
              <span className="num text-12 font-medium text-ink">{column.slot.label}</span>
              <span className="num text-12 text-ink-3">
                {column.departed ? "left" : hasPlan ? formatPct(share, 0) : formatKg(column.capacityKg)}
              </span>
            </span>
          )}
          <CapacityBar column={column} />
          <span className="sr-only">{capacityText(column)}</span>
        </button>
      </Tip>
    </div>
  );
}

function MarketLabel({ market, cardCount, kg }: { market: Market; cardCount: number; kg: number }): ReactElement {
  const name = shortMarket(market.name);
  const sub = market.name.slice(name.length).replace(/^\s*\(|\)\s*$/g, "");
  return (
    <div role="rowheader" className="sticky left-0 z-10 border-b border-line bg-surface px-3 py-2">
      <p className="truncate text-13 font-medium text-ink" title={market.name}>
        {name}
      </p>
      {sub ? <p className="truncate text-12 text-ink-3">{sub}</p> : null}
      <p className="mt-0.5 text-12 text-ink-3">
        {market.deliver_by_h !== null ? (
          <>
            order, on sale by <span className="num">{formatHours(market.deliver_by_h)}</span>
          </>
        ) : (
          <>
            <span className="num">{formatHours(market.travel_h)}</span> travel
          </>
        )}
      </p>
      {cardCount > 0 ? <p className="num mt-0.5 text-12 text-ink-3">{formatNumber(kg)} kg</p> : null}
    </div>
  );
}

export function PlanBoard({
  board,
  horizonH,
  hoveredId,
  changes,
  busy,
  containerRef,
  overlay,
  onOpen,
  onHover,
}: {
  board: BoardModel;
  horizonH: number;
  hoveredId: string | null;
  changes: Map<string, ChangeKind> | null;
  busy: boolean;
  containerRef: RefObject<HTMLDivElement>;
  overlay: ReactNode;
  onOpen: (batchId: string, trigger: HTMLElement) => void;
  onHover: (batchId: string | null) => void;
}): ReactElement {
  const template = [MARKET_COL, ...board.columns.map((c) => columnTrack(c, board.hasPlan))].join(" ");

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={containerRef}
        aria-busy={busy}
        className={cx(
          "scroll-quiet h-full overflow-auto transition-opacity duration-slow",
          busy && board.hasPlan && "opacity-50",
        )}
      >
        <div
          role="table"
          aria-label="Plan board: markets by departure slot"
          className="grid min-w-max"
          style={{ gridTemplateColumns: template }}
        >
          <div role="row" className="contents">
            <div
              role="columnheader"
              className="sticky left-0 top-0 z-30 flex items-end border-b border-line bg-surface px-3 pb-2 text-12 text-ink-3"
            >
              Market
            </div>
            {board.columns.map((column) => (
              <ColumnHeader key={column.slot.id} column={column} hasPlan={board.hasPlan} />
            ))}
          </div>
          {board.rows.map((row) => (
            <div role="row" key={row.market.id} className="contents">
              <MarketLabel market={row.market} cardCount={row.cardCount} kg={row.kg} />
              {board.columns.map((column) => {
                const cards = row.cells.get(column.slot.id) ?? [];
                return (
                  <div
                    role="cell"
                    key={column.slot.id}
                    className={cx(
                      "flex min-w-0 flex-col gap-1 border-b border-l border-line p-1",
                      column.departed && "bg-sunken",
                    )}
                  >
                    {cards.map((card) => (
                      <BatchCard
                        key={card.key}
                        card={card}
                        horizonH={horizonH}
                        highlighted={hoveredId === card.batchId}
                        change={changes?.get(card.batchId)}
                        onOpen={onOpen}
                        onHover={onHover}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      {overlay ? (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-start justify-center px-4 pt-24">
          <div className="pointer-events-auto w-full max-w-[480px]">{overlay}</div>
        </div>
      ) : null}
    </div>
  );
}
