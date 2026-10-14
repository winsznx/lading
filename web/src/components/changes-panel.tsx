import type { ReactElement } from "react";

import type { ReplanResponse } from "../api/types";
import { CHANGE_WORDS } from "../lib/codes";
import { formatInr, formatInrDelta } from "../lib/format";
import { Button, NumText, PanelTitle, Tag } from "./primitives";

export function ChangesPanel({
  response,
  open,
  busy,
  onDismiss,
  onReopen,
  onOpenBatch,
}: {
  response: ReplanResponse;
  open: boolean;
  busy: boolean;
  onDismiss: () => void;
  onReopen: () => void;
  onOpenBatch: (batchId: string, trigger: HTMLElement) => void;
}): ReactElement {
  const { changes } = response;
  const before = response.previous_net_inr;
  const after = response.lading.plan.expected.net_inr;

  if (!open) {
    return (
      <section aria-labelledby="changes-title" className="p-4">
        <PanelTitle
          id="changes-title"
          aside={
            <Button size="sm" variant="ghost" onClick={onReopen}>
              Show changes
            </Button>
          }
        >
          Changes
        </PanelTitle>
        <p className="mt-1 text-12 text-ink-3">
          <span className="num">{changes.length}</span> {changes.length === 1 ? "batch" : "batches"} changed. Highlights
          cleared.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="changes-title" aria-busy={busy} className="p-4">
      <PanelTitle
        id="changes-title"
        aside={
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        }
      >
        Changes <span className="num ml-1 font-normal text-ink-3">{changes.length}</span>
      </PanelTitle>
      <p className="mt-1 text-12 text-ink-2">
        <NumText text={response.disruption.label} />
      </p>
      <p className="mt-1 text-12 text-ink-3">
        Planned net <span className="num text-ink-2">{formatInr(before)}</span> →{" "}
        <span className="num text-ink-2">{formatInr(after)}</span>{" "}
        <span className="num whitespace-nowrap">({formatInrDelta(after - before)})</span>, plan estimates before and
        after the news
      </p>
      {changes.length === 0 ? (
        <p className="mt-3 text-13 text-ink-2">No batch needs to change.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-1">
          {changes.map((change) => (
            <li key={`${change.batch_id}-${change.kind}`}>
              <button
                type="button"
                data-batch-trigger=""
                onClick={(event) => {
                  onOpenBatch(change.batch_id, event.currentTarget);
                }}
                className="w-full rounded-sm border border-line bg-raised px-2 py-2 text-left hover:bg-highlight"
              >
                <span className="flex items-center gap-2">
                  <span className="num text-12 font-medium text-ink">{change.batch_id}</span>
                  <Tag>{CHANGE_WORDS[change.kind]}</Tag>
                </span>
                <span className="mt-1 block text-12 text-ink-2">
                  <NumText text={change.before} /> → <NumText text={change.after} className="text-ink" />
                </span>
                <span className="mt-0.5 block text-12 text-ink-3">
                  <NumText text={change.reason} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
