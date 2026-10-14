import type { ReactElement } from "react";

import type { SolveKind } from "../state/use-planner";
import { formatSeconds } from "../lib/format";

export function SolveChip({
  solving,
  expectedS,
  last,
}: {
  solving: SolveKind | null;
  expectedS: number | null;
  last: { kind: SolveKind; elapsedS: number } | null;
}): ReactElement {
  let body: ReactElement | null = null;
  if (solving) {
    const verb = solving === "plan" ? "planning" : "re-planning";
    body = (
      <span className="inline-flex h-6 items-center gap-2 rounded-sm border border-line-strong bg-raised px-2 text-12 text-ink">
        <span aria-hidden="true" className="h-2 w-2 rounded-sm bg-ink" />
        {expectedS === null ? (
          <span>{verb} · measuring…</span>
        ) : (
          <span>
            {verb} · <span className="num">~{formatSeconds(expectedS)}</span>
          </span>
        )}
      </span>
    );
  } else if (last) {
    body = (
      <span className="text-12 text-ink-3">
        {last.kind === "plan" ? "planned" : "re-planned"} in <span className="num">{formatSeconds(last.elapsedS)}</span>
      </span>
    );
  }
  return (
    <div role="status" aria-live="polite" className="flex h-8 w-[184px] shrink-0 items-center">
      {body}
    </div>
  );
}
