import * as Tabs from "@radix-ui/react-tabs";
import type { ReactElement, ReactNode } from "react";

import { useTheme } from "../lib/use-theme";
import { MoonIcon, SunIcon } from "./icons";
import { Kbd, Tip } from "./primitives";

export const TAGLINE = "Plans which produce goes where, when, and at what price, so less of it rots.";

function ThemeToggle(): ReactElement {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <Tip content={`Switch to ${next} theme`} side="bottom">
      <button
        type="button"
        onClick={toggle}
        aria-label={`Switch to ${next} theme`}
        className="inline-flex h-8 w-8 items-center justify-center rounded text-ink-2 hover:bg-highlight hover:text-ink"
      >
        {theme === "dark" ? <SunIcon /> : <MoonIcon />}
      </button>
    </Tip>
  );
}

const TAB_CLASS =
  "inline-flex h-7 items-center gap-2 rounded-sm px-2 text-13 text-ink-2 hover:text-ink data-[state=active]:bg-raised data-[state=active]:text-ink data-[state=active]:font-medium";

export function TopBar({
  controls,
  meta,
  withTabs = true,
}: {
  controls?: ReactNode;
  meta?: ReactNode;
  withTabs?: boolean;
}): ReactElement {
  return (
    <header className="shrink-0 border-b border-line bg-surface">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 lg:h-12 lg:flex-nowrap lg:py-0">
        <span
          className="order-1 select-none text-16 font-semibold tracking-tight text-ink"
          style={{ letterSpacing: "-0.02em" }}
        >
          Lading
        </span>
        <div className="order-3 flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-2 lg:order-2 lg:w-auto lg:flex-1 lg:flex-nowrap">
          {controls}
        </div>
        <div className="order-2 ml-auto flex items-center gap-1 lg:order-3">
          {withTabs ? (
            <Tabs.List
              aria-label="Views"
              className="flex items-center gap-px rounded border border-line bg-sunken p-px"
            >
              <Tabs.Trigger value="plan" className={TAB_CLASS}>
                Plan
              </Tabs.Trigger>
              <Tabs.Trigger value="evidence" className={TAB_CLASS}>
                Evidence <Kbd>E</Kbd>
              </Tabs.Trigger>
            </Tabs.List>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
      <div className="flex flex-col gap-1 border-t border-line px-4 py-2 lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-1">
        <p className="text-13 text-ink-2">{TAGLINE}</p>
        {meta}
      </div>
    </header>
  );
}
