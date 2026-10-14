"""The planning view of a scenario: timing, feasibility and truck capacity under a basis.

Every planning arm reads the world through this module so FEFO and Lading see the same facts.
`point` uses the forecast. `robust` uses P10 shelf life and P90 travel time, both derived from the
disclosed uncertainty block. The simulator and the validator don't use this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from scenarios.model import Batch, Market, Scenario, Slot

Z90 = 1.2815515655446004


def p10_shelf_h(scenario: Scenario, batch: Batch) -> float:
    sigma = scenario.commodity(batch.commodity_id).shelf_life_sigma
    return batch.shelf_life_h * max(0.4, 1.0 - Z90 * sigma)


def p90_travel_h(scenario: Scenario, market: Market) -> float:
    delay = scenario.uncertainty.travel_delay
    frac = delay.median_frac * math.exp(Z90 * delay.sigma_log) if delay.median_frac > 0 else 0.0
    return market.travel_h * (1.0 + frac)


@dataclass(frozen=True)
class World:
    scenario: Scenario
    basis: str

    def shelf_h(self, batch: Batch) -> float:
        return p10_shelf_h(self.scenario, batch) if self.basis == "robust" else batch.shelf_life_h

    def travel_h(self, market: Market) -> float:
        return p90_travel_h(self.scenario, market) if self.basis == "robust" else market.travel_h

    def sale_h(self, market: Market, slot: Slot) -> float:
        """Hours from t=0 until the stock is unloaded and on sale."""
        return slot.depart_h + self.travel_h(market) + market.handling_h

    @cached_property
    def open_slots(self) -> list[Slot]:
        return [s for s in self.scenario.slots if s.index >= self.scenario.policy.current_slot]

    def fresh_on_sale(self, batch: Batch, market: Market, slot: Slot) -> bool:
        """The hard constraint: on sale, inside any order deadline, before expiry minus the safety margin."""
        sale = self.sale_h(market, slot)
        if market.deliver_by_h is not None and sale > market.deliver_by_h:
            return False
        return sale <= self.shelf_h(batch) - self.scenario.policy.safety_margin_h

    def fresh_slots(self, batch: Batch, market: Market) -> list[Slot]:
        """Open slots from which the batch still arrives fresh. Later slots only get later, so this is
        always a prefix of the open slots."""
        return [s for s in self.open_slots if self.fresh_on_sale(batch, market, s)]

    def sells(self, batch: Batch, market: Market) -> bool:
        return self.scenario.offer(market.id, batch.commodity_id) is not None

    def dispatched_kg(self, batch: Batch) -> float:
        return sum(leg.kg for leg in self.scenario.controls.dispatched if leg.batch_id == batch.id)

    def on_hand_kg(self, batch: Batch) -> float:
        return max(batch.kg - self.dispatched_kg(batch), 0.0)

    def committed_market(self, batch: Batch) -> str | None:
        """A batch that has partly left follows its first load: the rest goes to the same market or stays."""
        return next((leg.market_id for leg in self.scenario.controls.dispatched if leg.batch_id == batch.id), None)

    def expires_in_horizon(self, batch: Batch) -> bool:
        return self.shelf_h(batch) <= self.scenario.policy.horizon_h

    def slot_capacity_kg(self, slot: Slot) -> float:
        """Trucks are hired per slot (PRD section 6). A truck marked out of service from a slot on
        doesn't count from then."""
        return sum(
            t.capacity_kg
            for t in self.scenario.trucks
            if t.unavailable_from_slot is None or slot.index < t.unavailable_from_slot
        )


def infeasible_batches(scenario: Scenario) -> list[str]:
    """INFEASIBLE_DEMAND: batches no buying market can receive fresh at any open slot, on the forecast."""
    world = World(scenario, "point")
    return [
        b.id
        for b in scenario.batches
        if not any(world.sells(b, m) and world.fresh_slots(b, m) for m in scenario.markets)
    ]
