export type RampStep = 0 | 1 | 2 | 3 | 4;

export interface RampBand {
  step: RampStep;
  label: string;
}

/**
 * Hours of saleable life left, banded against the planning horizon: fresh beyond the horizon, then halves
 * of it, then expired. The same bands colour inventory clocks and the margin left on plan cards.
 */
export function rampStep(hoursLeft: number, horizonH: number): RampStep {
  if (hoursLeft <= 0) return 4;
  if (hoursLeft < horizonH / 4) return 3;
  if (hoursLeft < horizonH / 2) return 2;
  if (hoursLeft < horizonH) return 1;
  return 0;
}

export function rampBands(horizonH: number): RampBand[] {
  const q = horizonH / 4;
  const h = horizonH / 2;
  return [
    { step: 0, label: `${horizonH}h+` },
    { step: 1, label: `${h}–${horizonH}h` },
    { step: 2, label: `${q}–${h}h` },
    { step: 3, label: `under ${q}h` },
    { step: 4, label: "expired" },
  ];
}

export const RAMP_FILL: Record<RampStep, string> = {
  0: "bg-ramp-0",
  1: "bg-ramp-1",
  2: "bg-ramp-2",
  3: "bg-ramp-3",
  4: "bg-ramp-4",
};

export const RAMP_WORD: Record<RampStep, string> = {
  0: "fresh",
  1: "inside the horizon",
  2: "at risk",
  3: "critical",
  4: "expired",
};
