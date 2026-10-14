import { memo, type ReactElement, useMemo } from "react";

import type { Scenario } from "../api/types";
import { cx } from "../lib/cx";
import { formatHours, formatKg, plural } from "../lib/format";
import { RAMP_FILL, RAMP_WORD, rampBands, rampStep } from "../lib/perishability";

interface RowProps {
  id: string;
  commodity: string;
  kg: number;
  origin: string;
  shelfH: number;
  horizonH: number;
  active: boolean;
  interactive: boolean;
  onHover: (id: string | null) => void;
  onOpen: (id: string, trigger: HTMLElement) => void;
}

const InventoryRow = memo(function InventoryRow({
  id,
  commodity,
  kg,
  origin,
  shelfH,
  horizonH,
  active,
  interactive,
  onHover,
  onOpen,
}: RowProps): ReactElement {
  const step = rampStep(shelfH, horizonH);
  const width = `${Math.max(2, Math.min(1, shelfH / horizonH) * 100)}%`;
  const body = (
    <>
      <span className="num col-start-1 row-start-1 text-12 text-ink-3">{id}</span>
      <span className="col-start-2 row-start-1 min-w-0 truncate text-13 text-ink">{commodity}</span>
      <span className="num col-start-3 row-start-1 text-right text-12 text-ink">{formatKg(kg)}</span>
      <span className="col-start-2 row-start-2 min-w-0 truncate text-12 text-ink-3" title={origin}>
        {origin}
      </span>
      <span className="num col-start-3 row-start-2 text-right text-12 text-ink-2">{formatHours(shelfH)}</span>
      <span
        aria-hidden="true"
        className="col-start-2 col-end-4 row-start-3 mt-1 block h-0.5 overflow-hidden rounded-sm bg-sunken"
      >
        <span className={cx("block h-full", RAMP_FILL[step])} style={{ width }} />
      </span>
      <span className="sr-only">
        , {formatHours(shelfH)} of shelf life left, {RAMP_WORD[step]}
      </span>
    </>
  );
  const grid = "grid w-full grid-cols-[28px_minmax(0,1fr)_auto] gap-x-2 border-b border-line px-3 pb-2 pt-2 text-left";
  if (!interactive) return <div className={grid}>{body}</div>;
  return (
    <button
      type="button"
      data-batch-trigger=""
      onMouseEnter={() => {
        onHover(id);
      }}
      onMouseLeave={() => {
        onHover(null);
      }}
      onFocus={() => {
        onHover(id);
      }}
      onBlur={() => {
        onHover(null);
      }}
      onClick={(event) => {
        onOpen(id, event.currentTarget);
      }}
      className={cx(grid, "transition-colors duration-fast hover:bg-highlight", active && "bg-highlight")}
    >
      {body}
    </button>
  );
});

export function InventoryRail({
  scenario,
  hoveredId,
  interactive,
  onHover,
  onOpen,
}: {
  scenario: Scenario;
  hoveredId: string | null;
  interactive: boolean;
  onHover: (id: string | null) => void;
  onOpen: (id: string, trigger: HTMLElement) => void;
}): ReactElement {
  const horizonH = scenario.policy.horizon_h;
  const rows = useMemo(() => {
    const names = new Map(scenario.commodities.map((c) => [c.id, c.name]));
    return scenario.batches
      .toSorted((a, b) => a.shelf_life_h - b.shelf_life_h || a.id.localeCompare(b.id))
      .map((b) => ({ ...b, commodity: names.get(b.commodity_id) ?? b.commodity_id }));
  }, [scenario]);
  const totalKg = rows.reduce((sum, b) => sum + b.kg, 0);

  return (
    <section aria-labelledby="inventory-title" className="flex min-h-0 flex-col">
      <div className="sticky top-0 z-10 border-b border-line bg-surface px-3 pb-2 pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 id="inventory-title" className="text-13 font-semibold text-ink">
            Inventory
          </h2>
          <span className="text-12 text-ink-3">
            {plural(rows.length, "batch", "batches")} · <span className="num">{formatKg(totalKg)}</span>
          </span>
        </div>
        <p className="mt-1 text-12 text-ink-3">
          Riskiest first. The bar under each batch is shelf life left, full at the{" "}
          <span className="num">{formatHours(horizonH)}</span> horizon.
        </p>
        <ul aria-label="Shelf life bands" className="mt-2 flex flex-wrap gap-x-2 gap-y-1">
          {rampBands(horizonH).map((band) => (
            <li key={band.step} className="flex items-center gap-1 text-12 text-ink-3">
              <span aria-hidden="true" className={cx("h-2 w-2 rounded-sm", RAMP_FILL[band.step])} />
              <span className="num">{band.label}</span>
            </li>
          ))}
        </ul>
      </div>
      <ul aria-label="Batches by shelf life left" className="min-h-0">
        {rows.map((b) => (
          <li key={b.id}>
            <InventoryRow
              id={b.id}
              commodity={b.commodity}
              kg={b.kg}
              origin={b.origin}
              shelfH={b.shelf_life_h}
              horizonH={horizonH}
              active={hoveredId === b.id}
              interactive={interactive}
              onHover={onHover}
              onOpen={onOpen}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
