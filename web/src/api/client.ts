import type {
  ApiErrorBody,
  Assumptions,
  Controls,
  PlannerConfig,
  PlanResponse,
  ReplanResponse,
  ResultFiles,
  ResultName,
  Scenario,
  ScenarioInfo,
} from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "").trim().replace(/\/+$/, "");

export class ApiError extends Error {
  readonly state: string;
  readonly path: string | null;
  readonly status: number | null;

  constructor(state: string, message: string, path: string | null = null, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.state = state;
    this.path = path;
    this.status = status;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const body = value as Record<string, unknown>;
  return typeof body.state === "string" && typeof body.message === "string";
}

const inflight = new Map<string, AbortController>();

/**
 * One AbortController per channel: starting a request on a channel cancels the one still running there,
 * so a newer plan or replan always wins over an older one.
 */
function claimChannel(channel: string, external?: AbortSignal): AbortSignal {
  inflight.get(channel)?.abort();
  const controller = new AbortController();
  inflight.set(channel, controller);
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", () => controller.abort(), { once: true });
  }
  return controller.signal;
}

function releaseChannel(channel: string, signal: AbortSignal): void {
  const current = inflight.get(channel);
  if (current?.signal === signal) inflight.delete(channel);
}

async function request<T>(channel: string, path: string, init: RequestInit, external?: AbortSignal): Promise<T> {
  if (!API_URL) {
    throw new ApiError("CONFIG", "Set VITE_API_URL to the planner API's address and rebuild the console.");
  }
  const signal = claimChannel(channel, external);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal,
      headers: init.body ? { "content-type": "application/json" } : undefined,
    });
  } catch (error) {
    releaseChannel(channel, signal);
    if (isAbortError(error)) throw error;
    throw new ApiError(
      "NETWORK",
      "The request never got an answer. Check that the API is running and allows this page's origin.",
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError("HTTP_ERROR", `The API answered ${response.status} without a JSON body.`, path, response.status);
  } finally {
    releaseChannel(channel, signal);
  }

  if (!response.ok) {
    if (isErrorBody(body)) throw new ApiError(body.state, body.message, body.path, response.status);
    throw new ApiError("HTTP_ERROR", `The API answered ${response.status}.`, path, response.status);
  }
  return body as T;
}

export function getScenarios(signal?: AbortSignal): Promise<ScenarioInfo[]> {
  return request<ScenarioInfo[]>("scenarios", "/scenarios", { method: "GET" }, signal);
}

export function getScenario(id: string, signal?: AbortSignal): Promise<Scenario> {
  return request<Scenario>("scenario", `/scenarios/${encodeURIComponent(id)}`, { method: "GET" }, signal);
}

export interface PlanRequest {
  scenario_id: string;
  controls: Controls;
}

export interface ReplanRequest extends PlanRequest {
  disruption_index: number;
}

export function plan(body: PlanRequest, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>("solve", "/plan", { method: "POST", body: JSON.stringify(body) }, signal);
}

export function replan(body: ReplanRequest, signal?: AbortSignal): Promise<ReplanResponse> {
  return request<ReplanResponse>("solve", "/replan", { method: "POST", body: JSON.stringify(body) }, signal);
}

export function getResult<K extends ResultName>(name: K, signal?: AbortSignal): Promise<ResultFiles[K]> {
  return request<ResultFiles[K]>(`result:${name}`, `/results/${name}.json`, { method: "GET" }, signal);
}

export function getAssumptions(signal?: AbortSignal): Promise<Assumptions> {
  return request<Assumptions>("assumptions", "/assumptions", { method: "GET" }, signal);
}

export function getConfig(signal?: AbortSignal): Promise<PlannerConfig> {
  return request<PlannerConfig>("config", "/config", { method: "GET" }, signal);
}
