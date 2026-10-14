import { type ReactElement, type ReactNode, useState } from "react";

import type { MetricKey, Quartiles } from "../api/types";
import { ErrorBoundary } from "../components/error-boundary";
import { CheckIcon, CopyIcon } from "../components/icons";
import { Button, ErrorNotice } from "../components/primitives";
import { cx } from "../lib/cx";
import { isNotFound } from "../lib/errors";
import { formatNumber } from "../lib/format";
import type { Resource } from "../lib/use-resource";
import { deltaTone, formatMetricDelta } from "./metrics";

export function Section({
  id,
  title,
  file,
  children,
  lede,
}: {
  id: string;
  title: string;
  file?: string;
  lede?: ReactNode;
  children: ReactNode;
}): ReactElement {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 border-t border-line pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={`${id}-title`} className="text-16 font-semibold text-ink">
          {title}
        </h2>
        {file ? <span className="num text-12 text-ink-3">results/{file}</span> : null}
      </div>
      {lede ? <p className="mt-1 max-w-[72ch] text-13 text-ink-2">{lede}</p> : null}
      <div className="mt-4">
        <ErrorBoundary what={`the ${title.toLowerCase()} section`}>{children}</ErrorBoundary>
      </div>
    </section>
  );
}

export function FileState<T>({
  resource,
  file,
  onRetry,
  children,
}: {
  resource: Resource<T>;
  file: string;
  onRetry: () => void;
  children: (data: T) => ReactNode;
}): ReactElement {
  if (resource.status === "loading") {
    return (
      <p role="status" className="text-13 text-ink-3">
        Loading <span className="num">{file}</span>…
      </p>
    );
  }
  if (resource.status === "error") {
    if (isNotFound(resource.error)) {
      return (
        <p className="rounded border border-dashed border-line-strong px-3 py-3 text-13 text-ink-2">
          Not generated yet: <span className="num">{file}</span> is missing. Run{" "}
          <code className="num">make reproduce</code>.
        </p>
      );
    }
    return <ErrorNotice error={resource.error} onRetry={onRetry} compact />;
  }
  return <>{children(resource.data)}</>;
}

export function QuartileCell({ metric, q }: { metric: MetricKey; q: Quartiles }): ReactElement {
  return (
    <div className="flex flex-col items-end">
      <span className={cx("num text-13 font-medium", deltaTone(metric, q.median))}>
        {formatMetricDelta(metric, q.median)}
      </span>
      <span className="num text-12 text-ink-3">
        {formatMetricDelta(metric, q.q1)} to {formatMetricDelta(metric, q.q3)}
      </span>
      <span className="text-12 text-ink-3">
        wins <span className="num">{formatNumber(q.wins)}</span>/<span className="num">{formatNumber(q.n)}</span>
      </span>
    </div>
  );
}

export function CopyCommand({ command }: { command: string }): ReactElement {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(command);
      setState("copied");
    } catch (error) {
      console.warn("Clipboard write refused", error);
      setState("failed");
    }
  }
  return (
    <div className="flex items-center gap-2">
      <pre className="num min-w-0 flex-1 overflow-x-auto rounded border border-line bg-sunken px-3 py-2 text-13 text-ink">
        <code>{command}</code>
      </pre>
      <Button
        onClick={() => {
          void copy();
        }}
        aria-label={`Copy ${command}`}
      >
        {state === "copied" ? <CheckIcon size={14} className="text-good" /> : <CopyIcon size={14} />}
        {state === "copied" ? "Copied" : state === "failed" ? "Select and copy" : "Copy"}
      </Button>
    </div>
  );
}

export function KeyValue({ rows }: { rows: { label: string; value: ReactNode }[] }): ReactElement {
  return (
    <dl className="grid grid-cols-[minmax(120px,200px)_minmax(0,1fr)] gap-x-4 text-13">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="border-t border-line py-2 text-ink-3">{row.label}</dt>
          <dd className="min-w-0 border-t border-line py-2 text-ink">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
