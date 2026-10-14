export type ScenarioKind = "held-out" | "control";

export type DisruptionKind = "route_delay" | "truck_loss" | "demand_spike" | "new_order";

export interface DisruptionInfo {
  index: number;
  kind: DisruptionKind;
  label: string;
  at_slot: number;
}

export interface ScenarioInfo {
  id: string;
  label: string;
  kind: ScenarioKind;
  note: string;
  seed: number | null;
  family: string;
  hub: string;
  batches: number;
  markets: number;
  trucks: number;
  stock_kg: number;
  live_verified: string | null;
  expected_solve_s: number | null;
  disruptions: DisruptionInfo[];
}

export interface Hub {
  id: string;
  name: string;
}

export interface Commodity {
  id: string;
  name: string;
  purchase_inr_per_kg: number;
  elasticity: number;
  shelf_life_sigma: number;
}

export interface Batch {
  id: string;
  commodity_id: string;
  kg: number;
  shelf_life_h: number;
  arrived_h_ago: number;
  origin: string;
}

export interface Offer {
  commodity_id: string;
  price_inr_per_kg: number;
  demand_kg: number;
}

export interface Market {
  id: string;
  name: string;
  travel_h: number;
  transport_inr_per_kg: number;
  handling_h: number;
  handling_inr_per_kg: number;
  deliver_by_h: number | null;
  offers: Offer[];
}

export interface Truck {
  id: string;
  capacity_kg: number;
  unavailable_from_slot: number | null;
}

export interface Slot {
  id: string;
  index: number;
  depart_h: number;
  label: string;
}

export interface Policy {
  horizon_h: number;
  safety_margin_h: number;
  discount_levels: number[];
  current_slot: number;
}

export interface Uncertainty {
  demand_sigma: number;
  travel_delay: { median_frac: number; sigma_log: number };
}

export interface Execution {
  route_delay: { market_id: string; extra_h: number } | null;
  demand_shock: { market_id: string; factor: number } | null;
  truck_loss: { truck_id: string; from_slot: number } | null;
  elasticity_factor: number;
}

export interface Lock {
  batch_id: string;
  market_id: string;
  slot_id: string;
}

export interface Veto {
  batch_id: string;
  market_id: string;
}

export interface Dispatched {
  batch_id: string;
  market_id: string;
  slot_id: string;
  kg: number;
}

export interface Controls {
  locks: Lock[];
  vetoes: Veto[];
}

export interface Scenario {
  schema_version: "lading-scenario-v1";
  id: string;
  label: string;
  source: "generator" | "organizer" | "curated";
  synthetic: boolean;
  seed: number | null;
  family: string;
  hub: Hub;
  cost_model: { id: string };
  commodities: Commodity[];
  batches: Batch[];
  markets: Market[];
  trucks: Truck[];
  slots: Slot[];
  policy: Policy;
  uncertainty: Uncertainty;
  execution: Execution;
  controls: Controls & { dispatched: Dispatched[] };
}

export type ArmName =
  | "fifo"
  | "fefo"
  | "lading-point"
  | "lading-robust"
  | "ablation-no-discount"
  | "ablation-soft-shelf"
  | "no-op";

export interface Shipment {
  batch_id: string;
  market_id: string;
  slot_id: string;
  kg: number;
  discount: number;
  locked: boolean;
}

export interface TripLoad {
  batch_id: string;
  market_id: string;
  kg: number;
}

export interface Trip {
  truck_id: string;
  slot_id: string;
  load_kg: number;
  manifest: TripLoad[];
}

export interface Price {
  market_id: string;
  commodity_id: string;
  discount: number;
}

export interface Expected {
  revenue_inr: number;
  discount_given_up_inr: number;
  transport_inr: number;
  handling_inr: number;
  spoilage_inr: number;
  net_inr: number;
  sold_kg: number;
  unsold_kg: number;
  expired_in_transit_kg: number;
  hub_spoiled_kg: number;
  carry_over_kg: number;
}

export interface SolverInfo {
  status: "OPTIMAL" | "TIME_LIMIT";
  objective_inr: number;
  bound_inr: number;
  gap: number;
  solve_s: number;
  n_vars: number;
  n_rows: number;
  highs_version: string;
}

export interface Plan {
  scenario_id: string;
  arm: ArmName;
  basis: "point" | "robust" | "none";
  shipments: Shipment[];
  trips: Trip[];
  prices: Price[];
  held: string[];
  infeasible: string[];
  expected: Expected;
  solver: SolverInfo | null;
}

export interface Violation {
  check: string;
  message: string;
  ref: string;
}

export interface Validation {
  status: "PASS" | "FAIL";
  violation_count: number;
  violations: Violation[];
  checks: Record<string, number>;
  recomputed: Expected;
}

export interface Outcome {
  spoiled_kg: number;
  expired_in_transit_kg: number;
  unsold_kg: number;
  hub_spoiled_kg: number;
  carry_over_kg: number;
  sold_kg: number;
  shipped_kg: number;
  cancelled_kg: number;
  demand_kg: number;
  demand_filled_pct: number;
  unmet_demand_kg: number;
  revenue_inr: number;
  discount_given_up_inr: number;
  transport_inr: number;
  handling_inr: number;
  spoilage_inr: number;
  net_inr: number;
  net_inr_p10: number;
  net_inr_p90: number;
  draws: number;
}

export interface ArmResult {
  arm: ArmName;
  plan: Plan;
  validation: Validation;
  outcome: Outcome;
}

export type AlternativeCode =
  | "EXPIRED_ON_ARRIVAL"
  | "DEADLINE"
  | "VETOED"
  | "TRUCK_FULL"
  | "DEMAND_MET"
  | "LOWER_NET"
  | "PLAN_TRADEOFF"
  | "HOLD";

export type HoldCode = "INFEASIBLE_DEMAND" | "TOO_RISKY" | "CARRY_OVER" | "NOT_WORTH_SHIPPING" | "NO_ROOM";

export interface Leg {
  slot_id: string;
  slot_label: string;
  kg: number;
  sale_h: number;
  margin_h: number;
}

export interface Alternative {
  market_id: string | null;
  market_name: string;
  code: AlternativeCode;
  sale_h: number | null;
  limit_h: number | null;
  deadline_h: number | null;
  last_slot_label: string | null;
  demand_left_kg: number | null;
  net_inr: number | null;
  delta_inr: number | null;
}

export interface Decision {
  batch_id: string;
  commodity_id: string;
  commodity_name: string;
  kg: number;
  origin: string;
  shelf_h: number;
  plan_shelf_h: number;
  basis: string;
  status: "assigned" | "held" | "infeasible";
  market_id: string | null;
  market_name: string | null;
  discount: number | null;
  legs: Leg[];
  net_inr: number;
  hold_code: HoldCode | null;
  locked: boolean;
  alternatives: Alternative[];
}

export interface Reason {
  headline: string;
  alternatives: string[];
}

export type SolverState = "OPTIMAL" | "SOLVER_TIMEOUT";

export interface PlanResponse {
  scenario: Scenario;
  lading: ArmResult;
  fefo: ArmResult;
  decisions: Decision[];
  reasons: Record<string, Reason>;
  effect: string;
  solve_s: number;
  elapsed_s: number;
  /** SOLVER_TIMEOUT: the live time budget ran out; the plan is the best found, gap in lading.plan.solver.gap. */
  solver_state: SolverState;
}

export interface NewOrder {
  id: string;
  name: string;
  commodity_id: string;
  kg: number;
  price_inr_per_kg: number;
  deliver_by_h: number;
  travel_h: number;
  transport_inr_per_kg: number;
  handling_h: number;
  handling_inr_per_kg: number;
}

export interface Disruption {
  kind: DisruptionKind;
  label: string;
  at_slot: number;
  market_id: string | null;
  extra_h: number | null;
  truck_id: string | null;
  commodity_id: string | null;
  factor: number | null;
  order: NewOrder | null;
}

export type ChangeKind = "moved" | "retimed" | "rediscounted" | "dropped" | "added";

export interface Change {
  batch_id: string;
  kind: ChangeKind;
  before: string;
  after: string;
  reason: string;
}

export interface ReplanResponse extends PlanResponse {
  disruption: Disruption;
  changes: Change[];
  previous_net_inr: number;
}

export interface ApiErrorBody {
  state: string;
  message: string;
  path: string | null;
}

export interface Quartiles {
  median: number;
  q1: number;
  q3: number;
  wins: number;
  losses?: number;
  n: number;
}

export interface MetricSummary {
  spoiled_kg: Quartiles;
  demand_filled_pct: Quartiles;
  net_inr: Quartiles;
}

export type MetricKey = keyof MetricSummary;

export interface RowArm {
  spoiled_kg: number;
  demand_filled_pct: number;
  net_inr: number;
  unmet_demand_kg: number;
  validator: "PASS" | "FAIL";
  violations: number;
  gap?: number;
}

export interface RowDelta {
  spoiled_kg: number;
  demand_filled_pct: number;
  net_inr: number;
}

export interface ResultRow {
  seed: number;
  scenario_id: string;
  hub: string;
  batches: number;
  stock_kg: number;
  arms: Record<string, RowArm>;
  delta: Record<string, RowDelta>;
}

export interface ValidatorTally {
  pass: number;
  fail: number;
  violations: number;
}

export interface HeldoutResults {
  headline_arm: string;
  draws_per_scenario: number;
  seeds: number[];
  arms: string[];
  rows: ResultRow[];
  summary: Record<string, MetricSummary>;
  validator: Record<string, ValidatorTally>;
}

export interface AblationSummary extends MetricSummary {
  vs: string;
  violations: number;
  plans_failing_validator: number;
}

export interface AblationResults {
  base_arm: string;
  rows: ResultRow[];
  summary: Record<string, AblationSummary>;
}

export interface StressFamily {
  description: string;
  seeds: number[];
  summary: Record<string, MetricSummary>;
  rows: ResultRow[];
  validator?: Record<string, ValidatorTally>;
}

export interface StressResults {
  draws_per_scenario?: number;
  families: Record<string, StressFamily>;
}

export interface SensitivityPoint extends MetricSummary {
  factor: number;
}

export interface SensitivityResults {
  arm: string;
  factors: number[];
  points: SensitivityPoint[];
  note?: string;
}

export interface ControlCheck {
  passed: boolean;
  detail: string;
  rule?: string;
  [extra: string]: unknown;
}

export type ControlsResults = Record<string, ControlCheck>;

export interface VerdictResults {
  headline_arm: string;
  falsifier: string;
  median_net_gain_inr: number;
  median_spoiled_delta_kg: number;
  median_fill_delta_pp?: number;
  triggered: boolean;
  verdict: string;
  statement: string;
  validator_violations: number;
}

export interface ManifestResults {
  commit: string;
  dirty: boolean;
  seeds: Record<string, unknown>;
  solver: { name: string; version: string; [setting: string]: unknown };
  cost_model_sha256: string;
  planner_config_sha256: string;
  python: string;
  libraries: Record<string, string>;
  host: string;
  draws_per_scenario: number;
  [extra: string]: unknown;
}

export interface TimingStat {
  median_s: number;
  p90_s?: number;
  max_s: number;
  n: number;
}

/** Groups such as heldout, stress, tuning or replan: either one stat or one per arm. */
export type TimingGroup = TimingStat | Record<string, TimingStat>;

export type TimingsResults = Record<string, TimingGroup | string>;

export interface CanonicalArm {
  outcome: Partial<Outcome> & Pick<Outcome, "spoiled_kg" | "demand_filled_pct" | "net_inr">;
  validation: { status: "PASS" | "FAIL"; violation_count: number };
  held?: number;
  shipments?: number;
}

export interface CanonicalResults {
  scenario_id: string;
  seed: number;
  draws: number;
  arms: Record<string, CanonicalArm>;
}

export interface ResultFiles {
  heldout: HeldoutResults;
  ablations: AblationResults;
  stress: StressResults;
  sensitivity: SensitivityResults;
  controls: ControlsResults;
  verdict: VerdictResults;
  manifest: ManifestResults;
  timings: TimingsResults;
  canonical: CanonicalResults;
}

export type ResultName = keyof ResultFiles;

export type Assumptions = Record<string, unknown>;

export interface PlannerConfig {
  headline_arm: string;
  planner: { live_time_limit_s?: number; [setting: string]: unknown };
}
