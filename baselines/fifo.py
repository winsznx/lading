"""FIFO: the weak reference arm (PRD section 5).

Decision rule, applied to batches in arrival order (longest at the hub first):

1. Look at markets that buy the commodity and still have forecast demand left at list price.
2. Take the one with the best list price. Freight, handling and shelf life are not considered.
3. Ship at the earliest open slot with truck room; if none, try the next-best price.
4. No discounts. A batch with no market and no truck stays at the hub.

It is reported once as a floor. It is not the bar Lading is measured against; FEFO is.
"""

from __future__ import annotations

from collections import defaultdict

from baselines.fleet import Fleet
from plan_assembly import assemble
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

    assignments: dict[str, tuple[str, str]] = {}
    for lock in scenario.controls.locks:
        b, m, s = scenario.batch(lock.batch_id), scenario.market(lock.market_id), scenario.slot(lock.slot_id)
        room = fleet.plan_room(m, s, b.kg)
        if room is not None:
            fleet.load(m, s, b.kg, room)
            assignments[b.id] = (m.id, s.id)
            remaining[(m.id, b.commodity_id)] -= b.kg

    for b in sorted(scenario.batches, key=lambda b: (-b.arrived_h_ago, b.id)):
        if b.id in assignments:
            continue
        markets = [
            m for m in scenario.markets
            if (b.id, m.id) not in vetoed and world.sells(b, m) and remaining[(m.id, b.commodity_id)] > 0
        ]
        markets.sort(key=lambda m: (-scenario.list_price(m.id, b.commodity_id), m.id))
        for m in markets:
            placed = False
            for s in world.open_slots:
                room = fleet.plan_room(m, s, b.kg)
                if room is not None:
                    fleet.load(m, s, b.kg, room)
                    assignments[b.id] = (m.id, s.id)
                    remaining[(m.id, b.commodity_id)] -= b.kg
                    placed = True
                    break
            if placed:
                break

    return assemble(scenario, "fifo", "point", assignments, dict(fleet.trucks_by_cell), {})
