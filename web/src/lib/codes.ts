import type { AlternativeCode, ChangeKind, DisruptionKind, HoldCode } from "../api/types";

export const HOLD_WORDS: Record<HoldCode, string> = {
  CARRY_OVER: "Kept for tomorrow",
  TOO_RISKY: "Too risky to ship",
  NOT_WORTH_SHIPPING: "Not worth shipping",
  NO_ROOM: "No room left",
  INFEASIBLE_DEMAND: "Can't be sold fresh",
};

export const ALTERNATIVE_WORDS: Record<AlternativeCode, string> = {
  EXPIRED_ON_ARRIVAL: "Expires before sale",
  DEADLINE: "Misses the order deadline",
  VETOED: "Vetoed",
  TRUCK_FULL: "Trucks full",
  DEMAND_MET: "Demand covered",
  LOWER_NET: "Lower net",
  PLAN_TRADEOFF: "Plan trade-off",
  HOLD: "Hold at hub",
};

export const DISRUPTION_WORDS: Record<DisruptionKind, string> = {
  route_delay: "Route delay",
  truck_loss: "Truck loss",
  demand_spike: "Demand spike",
  new_order: "New order",
};

export const CHANGE_WORDS: Record<ChangeKind, string> = {
  moved: "moved",
  retimed: "retimed",
  rediscounted: "re-priced",
  dropped: "now held",
  added: "now ships",
};

const ARM_WORDS: Record<string, string> = {
  "lading-point": "Lading, point",
  "lading-robust": "Lading, robust",
  fefo: "FEFO",
  fifo: "FIFO",
  "ablation-no-discount": "Ablation: no discount",
  "ablation-soft-shelf": "Ablation: soft shelf life",
  "no-op": "No-op",
};

export function armName(arm: string): string {
  return ARM_WORDS[arm] ?? arm;
}
