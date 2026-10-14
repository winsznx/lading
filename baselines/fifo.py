"""FIFO: the weak reference arm (PRD section 5).

Decision rule, applied to batches in arrival order (longest at the hub first):

1. Look at markets that buy the commodity and still have forecast demand left at list price.
2. Take the one with the best list price. Freight, handling and shelf life are not considered.
3. Ship in the earliest open slots with truck room; if the trucks are full, try the next-best price.
4. No discounts. A batch with no market and no truck room stays at the hub.

It is reported once as a floor. It is not the bar Lading is measured against; FEFO is.
"""

from __future__ import annotations

from collections import defaultdict

from baselines.fleet import Fleet
from plan_assembly import Leg, assemble
from plan_model import Plan
from scenarios.model import Scenario
from world import World


def plan_fifo(scenario: Scenario) -> Plan:
    world = World(scenario, "point")
    fleet = Fleet(world)
    vetoed = {(v.batch_id, v.market_id) for v in scenario.controls.vetoes}
    remaining: dict[tuple[str, str], float] = defaultdict(float)
    for m in scenario.markets:
        for o in m.offers:
            remaining[(m.id, o.commodity_id)] = o.demand_kg

    legs: list[Leg] = []
    placed: set[str] = set()
    for lock in scenario.controls.locks:
        b, s = scenario.batch(lock.batch_id), scenario.slot(lock.slot_id)
        parts = fleet.fit([s], b.kg)
        if parts is not None:
            fleet.take(parts)
            legs.append(Leg(b.id, lock.market_id, s.id, b.kg))
            remaining[(lock.market_id, b.commodity_id)] -= b.kg
            placed.add(b.id)

    for b in sorted(scenario.batches, key=lambda b: (-b.arrived_h_ago, b.id)):
        if b.id in placed:
            continue
        markets = [
            m
            for m in scenario.markets
            if (b.id, m.id) not in vetoed and world.sells(b, m) and remaining[(m.id, b.commodity_id)] > 0
        ]
        markets.sort(key=lambda m: (-scenario.list_price(m.id, b.commodity_id), m.id))
        for m in markets:
            parts = fleet.fit(world.open_slots, b.kg)
            if parts is None:
                continue
            fleet.take(parts)
            legs += [Leg(b.id, m.id, s.id, kg) for s, kg in parts]
            remaining[(m.id, b.commodity_id)] -= b.kg
            break

    return assemble(scenario, "fifo", "point", legs, {})
