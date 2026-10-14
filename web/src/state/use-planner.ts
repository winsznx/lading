import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from "react";

import { isAbortError, plan, replan } from "../api/client";
import type { Controls, PlanResponse, ReplanResponse } from "../api/types";

export type SolveKind = "plan" | "replan";

export interface Solved {
  kind: SolveKind;
  response: PlanResponse | ReplanResponse;
  controls: Controls;
  disruptionIndex: number | null;
  seq: number;
}

export interface Solving {
  kind: SolveKind;
  controls: Controls;
  disruptionIndex: number | null;
}

export interface Failure {
  error: unknown;
  request: Solving;
}

export interface PlannerState {
  current: Solved | null;
  base: Solved | null;
  solving: Solving | null;
  failure: Failure | null;
  diffOpen: boolean;
  lastElapsed: Record<SolveKind, number | null>;
  seq: number;
}

type Action =
  | { type: "start"; solving: Solving }
  | { type: "success"; solving: Solving; response: PlanResponse | ReplanResponse }
  | { type: "failure"; failure: Failure }
  | { type: "restore-base" }
  | { type: "dismiss-diff" }
  | { type: "reopen-diff" }
  | { type: "dismiss-failure" };

export const NO_CONTROLS: Controls = { locks: [], vetoes: [] };

const INITIAL: PlannerState = {
  current: null,
  base: null,
  solving: null,
  failure: null,
  diffOpen: false,
  lastElapsed: { plan: null, replan: null },
  seq: 0,
};

function reducer(state: PlannerState, action: Action): PlannerState {
  switch (action.type) {
    case "start":
      return { ...state, solving: action.solving, failure: null };
    case "success": {
      const seq = state.seq + 1;
      const solved: Solved = { ...action.solving, response: action.response, seq };
      return {
        ...state,
        seq,
        current: solved,
        base: action.solving.kind === "plan" ? solved : state.base,
        solving: null,
        failure: null,
        diffOpen: action.solving.kind === "replan",
        lastElapsed: { ...state.lastElapsed, [action.solving.kind]: action.response.elapsed_s },
      };
    }
    case "failure":
      return { ...state, solving: null, failure: action.failure };
    case "restore-base": {
      if (!state.base) return state;
      const seq = state.seq + 1;
      return { ...state, seq, current: { ...state.base, seq }, diffOpen: false, failure: null };
    }
    case "dismiss-diff":
      return { ...state, diffOpen: false };
    case "reopen-diff":
      return { ...state, diffOpen: state.current?.kind === "replan" };
    case "dismiss-failure":
      return { ...state, failure: null };
  }
}

export function sameControls(a: Controls, b: Controls): boolean {
  const key = (c: Controls): string =>
    JSON.stringify({
      locks: c.locks.map((l) => `${l.batch_id}>${l.market_id}@${l.slot_id}`).toSorted(),
      vetoes: c.vetoes.map((v) => `${v.batch_id}x${v.market_id}`).toSorted(),
    });
  return key(a) === key(b);
}

export interface Planner {
  state: PlannerState;
  /** Controls as the dispatcher sees them: the pending set while solving, else the solved plan's. */
  controls: Controls;
  activeDisruption: number | null;
  runPlan: () => void;
  runDisruption: (index: number) => void;
  applyControls: (next: Controls) => void;
  resetToBase: () => void;
  retry: () => void;
  reopenDiff: () => void;
  dismissDiff: () => void;
  dismissFailure: () => void;
}

export function usePlanner(scenarioId: string, beforeCommit: () => void): Planner {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const unmountSignal = useRef<AbortController | null>(null);
  const beforeCommitRef = useRef(beforeCommit);
  useLayoutEffect(() => {
    beforeCommitRef.current = beforeCommit;
  });

  useEffect(() => {
    const controller = new AbortController();
    unmountSignal.current = controller;
    return () => {
      controller.abort();
    };
  }, []);

  const solve = useCallback(
    async (solving: Solving): Promise<void> => {
      dispatch({ type: "start", solving });
      const signal = unmountSignal.current?.signal;
      try {
        const response =
          solving.kind === "plan" || solving.disruptionIndex === null
            ? await plan({ scenario_id: scenarioId, controls: solving.controls }, signal)
            : await replan(
                { scenario_id: scenarioId, disruption_index: solving.disruptionIndex, controls: solving.controls },
                signal,
              );
        beforeCommitRef.current();
        dispatch({ type: "success", solving, response });
      } catch (error) {
        if (isAbortError(error)) return;
        dispatch({ type: "failure", failure: { error, request: solving } });
      }
    },
    [scenarioId],
  );

  const controls = state.solving?.controls ?? state.current?.controls ?? NO_CONTROLS;
  const activeDisruption = state.solving ? state.solving.disruptionIndex : (state.current?.disruptionIndex ?? null);

  const runPlan = useCallback(() => {
    void solve({ kind: "plan", controls, disruptionIndex: null });
  }, [solve, controls]);

  const runDisruption = useCallback(
    (index: number) => {
      void solve({ kind: "replan", controls, disruptionIndex: index });
    },
    [solve, controls],
  );

  const applyControls = useCallback(
    (next: Controls) => {
      void solve({
        kind: activeDisruption === null ? "plan" : "replan",
        controls: next,
        disruptionIndex: activeDisruption,
      });
    },
    [solve, activeDisruption],
  );

  const { base } = state;
  const idle = state.solving === null;
  const resetToBase = useCallback(() => {
    if (idle && base && sameControls(base.controls, controls)) {
      beforeCommitRef.current();
      dispatch({ type: "restore-base" });
      return;
    }
    void solve({ kind: "plan", controls, disruptionIndex: null });
  }, [idle, base, controls, solve]);

  const { failure } = state;
  const retry = useCallback(() => {
    if (failure) void solve(failure.request);
  }, [failure, solve]);
  const reopenDiff = useCallback(() => {
    dispatch({ type: "reopen-diff" });
  }, []);
  const dismissDiff = useCallback(() => {
    dispatch({ type: "dismiss-diff" });
  }, []);
  const dismissFailure = useCallback(() => {
    dispatch({ type: "dismiss-failure" });
  }, []);

  return {
    state,
    controls,
    activeDisruption,
    runPlan,
    runDisruption,
    applyControls,
    resetToBase,
    retry,
    reopenDiff,
    dismissDiff,
    dismissFailure,
  };
}
