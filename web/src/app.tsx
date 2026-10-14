import * as Tooltip from "@radix-ui/react-tooltip";
import { type ReactElement, useState } from "react";

import { API_URL, getScenarios } from "./api/client";
import type { ScenarioInfo } from "./api/types";
import { Console } from "./components/console";
import { ErrorNotice } from "./components/primitives";
import { TopBar } from "./components/top-bar";
import { useResource } from "./lib/use-resource";

const PRESELECTED = "heldout-1007";

function defaultScenario(list: ScenarioInfo[]): string | null {
  return (
    list.find((s) => s.id === PRESELECTED)?.id ?? list.find((s) => s.kind === "held-out")?.id ?? list[0]?.id ?? null
  );
}

function Shell({ children }: { children: ReactElement }): ReactElement {
  return (
    <div className="flex min-h-dvh flex-col">
      <TopBar withTabs={false} />
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}

export function App(): ReactElement {
  const [scenarios, reload] = useResource("scenarios", getScenarios);
  const [chosen, setChosen] = useState<string | null>(null);

  let body: ReactElement;
  if (scenarios.status === "loading") {
    body = (
      <Shell>
        <p role="status" className="text-13 text-ink-3">
          Loading curated scenarios from <span className="num">{API_URL || "the planner API"}</span>…
        </p>
      </Shell>
    );
  } else if (scenarios.status === "error") {
    body = (
      <Shell>
        <div className="max-w-[640px]">
          <ErrorNotice error={scenarios.error} onRetry={reload} />
        </div>
      </Shell>
    );
  } else {
    const list = scenarios.data;
    const scenarioId = chosen && list.some((s) => s.id === chosen) ? chosen : defaultScenario(list);
    body =
      scenarioId === null ? (
        <Shell>
          <p className="text-13 text-ink-2">The planner API has no curated scenarios to plan.</p>
        </Shell>
      ) : (
        <Console key={scenarioId} scenarios={list} scenarioId={scenarioId} onSelectScenario={setChosen} />
      );
  }

  return (
    <Tooltip.Provider delayDuration={250} skipDelayDuration={100}>
      {body}
    </Tooltip.Provider>
  );
}
