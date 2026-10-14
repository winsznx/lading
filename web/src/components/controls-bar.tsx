import type { ReactElement, ReactNode } from "react";

import type { Controls, Lock, Scenario, Veto } from "../api/types";
import { shortMarket } from "../lib/format";
import { CloseIcon, LockIcon } from "./icons";
import { Tag } from "./primitives";

function Chip({
  children,
  onRemove,
  label,
}: {
  children: ReactNode;
  onRemove: () => void;
  label: string;
}): ReactElement {
  return (
    <li className="inline-flex h-6 shrink-0 items-center gap-1 rounded-sm border border-line-strong bg-raised pl-2 text-12 text-ink">
      {children}
      <button
        type="button"
        onClick={onRemove}
        aria-label={label}
        className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-ink-3 hover:bg-highlight hover:text-ink"
      >
        <CloseIcon size={12} />
      </button>
    </li>
  );
}

export function ControlsBar({
  scenario,
  controls,
  status,
  onRemoveLock,
  onRemoveVeto,
}: {
  scenario: Scenario;
  controls: Controls;
  status: string;
  onRemoveLock: (lock: Lock) => void;
  onRemoveVeto: (veto: Veto) => void;
}): ReactElement {
  const market = new Map(scenario.markets.map((m) => [m.id, shortMarket(m.name)]));
  const slot = new Map(scenario.slots.map((s) => [s.id, s.label]));
  const count = controls.locks.length + controls.vetoes.length;

  return (
    <div className="flex min-h-10 shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-3 py-1">
      <h2 className="text-13 font-semibold text-ink">Plan board</h2>
      <Tag>{status}</Tag>
      {count === 0 ? (
        <span className="text-12 text-ink-3">No locks or vetoes</span>
      ) : (
        <ul aria-label="Dispatcher locks and vetoes" className="flex min-w-0 flex-wrap items-center gap-1">
          {controls.locks.map((lock) => (
            <Chip
              key={`lock-${lock.batch_id}`}
              label={`Remove lock on ${lock.batch_id}`}
              onRemove={() => {
                onRemoveLock(lock);
              }}
            >
              <LockIcon size={12} className="text-ink-2" />
              <span>
                <span className="num">{lock.batch_id}</span> → {market.get(lock.market_id) ?? lock.market_id},{" "}
                <span className="num">{slot.get(lock.slot_id) ?? lock.slot_id}</span>
              </span>
            </Chip>
          ))}
          {controls.vetoes.map((veto) => (
            <Chip
              key={`veto-${veto.batch_id}-${veto.market_id}`}
              label={`Remove veto on ${veto.batch_id} at ${market.get(veto.market_id) ?? veto.market_id}`}
              onRemove={() => {
                onRemoveVeto(veto);
              }}
            >
              <span>
                Veto <span className="num">{veto.batch_id}</span> at {market.get(veto.market_id) ?? veto.market_id}
              </span>
            </Chip>
          ))}
        </ul>
      )}
      <span className="ml-auto hidden text-12 text-ink-3 xl:inline">
        Card: on sale <span aria-hidden="true">→</span> shelf life ends, margin left
      </span>
    </div>
  );
}
