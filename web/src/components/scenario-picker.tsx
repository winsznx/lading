import * as Popover from "@radix-ui/react-popover";
import { type ReactElement, useState } from "react";

import type { ScenarioInfo } from "../api/types";
import { cx } from "../lib/cx";
import { formatKg } from "../lib/format";
import { ChevronDownIcon } from "./icons";
import { Tag } from "./primitives";

function KindTag({ kind }: { kind: ScenarioInfo["kind"] }): ReactElement {
  return <Tag tone={kind === "held-out" ? "strong" : "neutral"}>{kind === "held-out" ? "held-out" : "control"}</Tag>;
}

export function ScenarioPicker({
  scenarios,
  selectedId,
  onSelect,
}: {
  scenarios: ScenarioInfo[];
  selectedId: string;
  onSelect: (id: string) => void;
}): ReactElement {
  const [open, setOpen] = useState(false);
  const selected = scenarios.find((s) => s.id === selectedId);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="flex h-8 w-full min-w-0 items-center gap-2 rounded border border-line-strong bg-raised pl-2 pr-1 text-left hover:bg-highlight lg:w-auto lg:max-w-[420px]"
        >
          <span className="min-w-0 truncate text-13 text-ink">{selected?.label ?? "Choose a scenario"}</span>
          {selected ? <KindTag kind={selected.kind} /> : null}
          <span className="sr-only">, change scenario</span>
          <ChevronDownIcon className="shrink-0 text-ink-3" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          collisionPadding={16}
          className="popover z-40 w-[440px] max-w-[calc(100vw-32px)] rounded-md border border-line bg-raised p-1 shadow-overlay"
        >
          <p className="px-2 pb-1 pt-1 text-12 text-ink-3">Curated scenarios on the planner API. Synthetic data.</p>
          <ul className="flex flex-col gap-px">
            {scenarios.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  aria-current={s.id === selectedId}
                  onClick={() => {
                    setOpen(false);
                    if (s.id !== selectedId) onSelect(s.id);
                  }}
                  className={cx(
                    "w-full rounded px-2 py-2 text-left hover:bg-highlight",
                    s.id === selectedId && "bg-highlight",
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-13 font-medium text-ink">{s.label}</span>
                    <KindTag kind={s.kind} />
                  </span>
                  <span className="mt-1 block text-12 text-ink-2">{s.note}</span>
                  <span className="mt-1 flex flex-wrap gap-x-3 text-12 text-ink-3">
                    <span>{s.hub}</span>
                    <span>
                      <span className="num">{s.batches}</span> batches
                    </span>
                    <span>
                      <span className="num">{s.markets}</span> markets
                    </span>
                    <span>
                      <span className="num">{s.trucks}</span> trucks
                    </span>
                    <span className="num">{formatKg(s.stock_kg)}</span>
                    {s.seed !== null ? (
                      <span>
                        seed <span className="num">{s.seed}</span>
                      </span>
                    ) : null}
                    {s.live_verified ? (
                      <span>
                        live-verified <span className="num">{s.live_verified}</span>
                      </span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
