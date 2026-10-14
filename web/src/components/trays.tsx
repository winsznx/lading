import type { ReactElement } from "react";

import type { TrayItem } from "../lib/board";
import { HOLD_WORDS } from "../lib/codes";
import { cx } from "../lib/cx";
import { formatHours, formatKg, formatNumber } from "../lib/format";
import { NumText } from "./primitives";

function Tray({
  id,
  title,
  items,
  empty,
  onOpen,
  grow,
}: {
  id: string;
  title: string;
  items: TrayItem[];
  empty: string;
  onOpen: (batchId: string, trigger: HTMLElement) => void;
  grow: boolean;
}): ReactElement {
  const kg = items.reduce((sum, item) => sum + item.kg, 0);
  return (
    <section aria-labelledby={id} className={cx("min-w-0", grow ? "flex-1" : "lg:w-[240px] lg:shrink-0")}>
      <div className="flex items-baseline gap-2">
        <h3 id={id} className="text-12 font-semibold text-ink">
          {title}
        </h3>
        <span className="text-12 text-ink-3">
          <span className="num">{items.length}</span> {items.length === 1 ? "batch" : "batches"}
          {items.length > 0 ? (
            <>
              {" "}
              · <span className="num">{formatKg(kg)}</span>
            </>
          ) : null}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="mt-1 text-12 text-ink-3">{empty}</p>
      ) : (
        <ul className="scroll-quiet mt-1 flex gap-2 overflow-x-auto pb-1">
          {items.map((item) => (
            <li key={item.batchId} className="w-[264px] shrink-0">
              <button
                type="button"
                data-batch-trigger=""
                onClick={(event) => {
                  onOpen(item.batchId, event.currentTarget);
                }}
                className="flex h-full w-full flex-col gap-0.5 rounded-sm border border-line bg-raised px-2 py-1 text-left hover:border-line-strong"
              >
                <span className="flex items-center justify-between gap-2 text-12">
                  <span className="min-w-0 truncate text-ink">
                    <span className="num font-medium">{item.batchId}</span>
                    <span className="text-ink-3"> · </span>
                    {item.commodity}
                    <span className="text-ink-3"> · </span>
                    <span className="num">{formatNumber(item.kg)}</span> kg
                  </span>
                  <span className="num shrink-0 text-ink-3">{formatHours(item.shelfH)} left</span>
                </span>
                <NumText
                  text={item.reason || (item.holdCode ? HOLD_WORDS[item.holdCode] : "")}
                  className="line-clamp-2 text-12 text-ink-2"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function Trays({
  held,
  infeasible,
  onOpen,
}: {
  held: TrayItem[];
  infeasible: TrayItem[];
  onOpen: (batchId: string, trigger: HTMLElement) => void;
}): ReactElement {
  return (
    <div className="flex flex-col gap-3 border-t border-line px-3 py-2 lg:flex-row lg:gap-4">
      <Tray
        id="tray-held"
        title="Held at hub"
        items={held}
        empty="Every batch ships in this plan."
        onOpen={onOpen}
        grow
      />
      <Tray
        id="tray-infeasible"
        title="Can't be sold fresh"
        items={infeasible}
        empty="Every batch can reach some market fresh."
        onOpen={onOpen}
        grow={infeasible.length > 0}
      />
    </div>
  );
}
