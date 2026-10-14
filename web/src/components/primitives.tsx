import * as Tooltip from "@radix-ui/react-tooltip";
import { type ButtonHTMLAttributes, forwardRef, type ReactElement, type ReactNode } from "react";

import { cx } from "../lib/cx";
import { describeError } from "../lib/errors";
import { AlertIcon } from "./icons";

export function Kbd({
  children,
  className,
  inverse = false,
}: {
  children: ReactNode;
  className?: string;
  inverse?: boolean;
}): ReactElement {
  return (
    <kbd
      className={cx(
        "num inline-flex h-4 min-w-4 items-center justify-center rounded-sm border px-1 text-12 font-normal leading-none",
        inverse ? "border-accent-ink text-accent-ink" : "border-line text-ink-3",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink hover:bg-accent-hover disabled:opacity-60",
  secondary:
    "border border-line-strong bg-raised text-ink hover:bg-highlight disabled:text-ink-3 disabled:hover:bg-raised",
  ghost: "text-ink-2 hover:bg-highlight hover:text-ink disabled:text-ink-3 disabled:hover:bg-transparent",
  danger: "border border-line-strong bg-raised text-bad hover:bg-bad-wash disabled:text-ink-3",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", className, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded font-medium transition-colors duration-fast",
        size === "md" ? "h-8 px-3 text-13" : "h-7 px-2 text-12",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
});

export function Tag({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "lading" | "good" | "bad" | "strong";
  className?: string;
}): ReactElement {
  const tones = {
    neutral: "border-line text-ink-2",
    strong: "border-ink text-ink",
    lading: "border-transparent bg-lading-wash text-lading",
    good: "border-transparent bg-good-wash text-good",
    bad: "border-transparent bg-bad-wash text-bad",
  } as const;
  return (
    <span
      className={cx(
        "inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-sm border px-1 text-12 font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Tip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}): ReactElement {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className="tooltip z-50 max-w-[280px] rounded border border-line bg-raised px-2 py-1 text-12 text-ink shadow-overlay"
        >
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Swatch({ series }: { series: "lading" | "fefo" }): ReactElement {
  return (
    <span
      aria-hidden="true"
      className={cx("inline-block h-2 w-2 shrink-0 rounded-sm", series === "lading" ? "bg-lading" : "bg-fefo")}
    />
  );
}

const NUMBER_TOKEN = /(D\d+ \d{2}:\d{2}|\bb\d+\b|[+−-]?₹?\d[\d,]*(?:\.\d+)?(?:\s?(?:kg|pp|h|t|s)\b|%)?)/g;

/** Sentence text from the API with every number set in the numeric face. */
export function NumText({ text, className }: { text: string; className?: string }): ReactElement {
  const parts = text.split(NUMBER_TOKEN);
  return (
    <span className={className}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} className="num">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </span>
  );
}

export function ErrorNotice({
  error,
  onRetry,
  onDismiss,
  footnote,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  onDismiss?: () => void;
  footnote?: ReactNode;
  compact?: boolean;
}): ReactElement {
  const copy = describeError(error);
  return (
    <div
      role="alert"
      className={cx("flex items-start gap-3 rounded border border-bad bg-bad-wash text-ink", compact ? "p-2" : "p-3")}
    >
      <AlertIcon className="mt-0.5 shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <p className="text-13 font-semibold">{copy.title}</p>
        <p className="mt-0.5 text-13 text-ink-2">
          <NumText text={copy.message} />
        </p>
        <p className="num mt-1 text-12 text-ink-3">{copy.state}</p>
        {footnote ? <p className="mt-1 text-12 text-ink-2">{footnote}</p> : null}
      </div>
      {onRetry || onDismiss ? (
        <div className="flex shrink-0 gap-1">
          {onRetry ? (
            <Button size="sm" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
          {onDismiss ? (
            <Button size="sm" variant="ghost" onClick={onDismiss}>
              Dismiss
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function PanelTitle({
  id,
  children,
  aside,
}: {
  id?: string;
  children: ReactNode;
  aside?: ReactNode;
}): ReactElement {
  return (
    <div className="flex min-h-6 items-center justify-between gap-2">
      <h2 id={id} className="text-13 font-semibold text-ink">
        {children}
      </h2>
      {aside}
    </div>
  );
}
