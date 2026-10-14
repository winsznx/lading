"""Realized worlds for execution.

Draws come from their own seed stream (EXEC_STREAM) so plan-time and outcome randomness never share
state. Each entity kind gets a child stream, and draws are indexed by scenario entities, never by
plan contents, so every arm executes against exactly the same realized day.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from scenarios.model import Scenario

EXEC_STREAM = 202
_SHELF, _TRAVEL, _DEMAND = 1, 2, 3


@dataclass(frozen=True)
class Realization:
    label: str
    shelf_h: dict[str, float]
    travel_h: dict[tuple[str, str], float]
    demand_kg: dict[tuple[str, str], float]
    elasticity: dict[str, float]
    truck_lost_from_slot: dict[str, int]


def scenario_seed(scenario: Scenario) -> int:
    if scenario.seed is not None:
        return scenario.seed
    return int.from_bytes(hashlib.sha256(scenario.id.encode()).digest()[:4], "big")


def forecast(scenario: Scenario) -> Realization:
    """The world exactly as forecast, with no execution shocks. Used for every arm's expected totals."""
    return Realization(
        label="forecast",
        shelf_h={b.id: b.shelf_life_h for b in scenario.batches},
        travel_h={(m.id, s.id): m.travel_h for m in scenario.markets for s in scenario.slots},
        demand_kg={(m.id, o.commodity_id): o.demand_kg for m in scenario.markets for o in m.offers},
        elasticity={c.id: c.elasticity for c in scenario.commodities},
        truck_lost_from_slot={},
    )


def realize(scenario: Scenario, draw: int) -> Realization:
    seed = scenario_seed(scenario)

    def stream(kind: int) -> np.random.Generator:
        return np.random.default_rng(np.random.SeedSequence([seed, EXEC_STREAM, draw, kind]))

    ex = scenario.execution
    shelf_rng = stream(_SHELF)
    shelf = {}
    for b in scenario.batches:
        sigma = scenario.commodity(b.commodity_id).shelf_life_sigma
        shelf[b.id] = b.shelf_life_h * float(np.clip(1.0 + sigma * shelf_rng.standard_normal(), 0.4, 1.6))

    delay = scenario.uncertainty.travel_delay
    travel_rng = stream(_TRAVEL)
    travel = {}
    for m in scenario.markets:
        extra = ex.route_delay.extra_h if ex.route_delay and ex.route_delay.market_id == m.id else 0.0
        for s in scenario.slots:
            z = travel_rng.standard_normal()
            frac = delay.median_frac * float(np.exp(delay.sigma_log * z)) if delay.median_frac > 0 else 0.0
            travel[(m.id, s.id)] = m.travel_h * (1.0 + frac) + extra

    demand_rng = stream(_DEMAND)
    demand = {}
    sigma_d = scenario.uncertainty.demand_sigma
    for m in scenario.markets:
        shock = ex.demand_shock.factor if ex.demand_shock and ex.demand_shock.market_id == m.id else 1.0
        for o in m.offers:
            noise = float(np.clip(1.0 + sigma_d * demand_rng.standard_normal(), 0.2, 2.0))
            demand[(m.id, o.commodity_id)] = o.demand_kg * noise * shock

    lost = {ex.truck_loss.truck_id: ex.truck_loss.from_slot} if ex.truck_loss else {}
    return Realization(
        label=f"draw-{draw}",
        shelf_h=shelf,
        travel_h=travel,
        demand_kg=demand,
        elasticity={c.id: c.elasticity * ex.elasticity_factor for c in scenario.commodities},
        truck_lost_from_slot=lost,
    )
