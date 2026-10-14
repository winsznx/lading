import { API_URL, ApiError } from "../api/client";

const TITLES: Record<string, string> = {
  SOLVER_TIMEOUT: "The planner ran out of time",
  LOCK_INFEASIBLE: "That lock can't hold",
  RATE_LIMITED: "Too many requests",
  VALIDATOR_FAIL: "Plan rejected by the independent validator",
  SCHEMA_INVALID: "The scenario has a bad field",
  SOLVER_UNAVAILABLE: "The planner is busy",
  SCENARIO_NOT_FOUND: "Not found on the planner API",
  SCENARIO_TOO_LARGE: "The scenario is too large for the live planner",
  INFEASIBLE_DEMAND: "No market can take this stock fresh",
  NO_TRUCK: "No truck is available",
  INTERNAL_ERROR: "The planner API hit an internal error",
  HTTP_ERROR: "The planner API sent an unexpected answer",
  CONFIG: "The console has no API address",
};

export interface ErrorCopy {
  state: string;
  title: string;
  message: string;
}

export function describeError(error: unknown): ErrorCopy {
  if (error instanceof ApiError) {
    if (error.state === "NETWORK") {
      return { state: error.state, title: `Can't reach the planner API at ${API_URL}`, message: error.message };
    }
    return {
      state: error.state,
      title: TITLES[error.state] ?? `The planner API reported ${error.state}`,
      message: error.message,
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { state: "CLIENT_ERROR", title: "The console hit an unexpected error", message };
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.state === "SCENARIO_NOT_FOUND";
}
