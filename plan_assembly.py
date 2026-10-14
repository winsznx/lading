"""Turn an arm's decisions into a Plan: truck manifests, prices, held stock and forecast totals.

Every arm goes through `assemble`, so trips are packed and totals booked the same way for all of them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from plan_model import Arm, Basis, Plan, Price, Shipment, SolverInfo, Trip, TripLoad
from scenarios.model import Scenario
from sim.simulator import expected
from world import infeasible_batches

Cell = tuple[str, str]


def pack_trips(
    scenario: Scenario, shipments: list[Shipment], trucks_by_cell: dict[Cell, list[str]]
) -> list[Trip]:
    """Load each (market, slot) cell's batches onto its trucks in order, splitting a batch across trucks
    when one fills up. Crates split freely between two trucks going to the same place at the same time."""
    capacity = {t.id: t.capacity_kg for t in scenario.trucks}
    by_cell: dict[Cell, list[Shipment]] = defaultdict(list)
    for sh in shipments:
        by_cell[(sh.market_id, sh.slot_id)].append(sh)

    trips: list[Trip] = []
    slot_index = {s.id: s.index for s in scenario.slots}
    for cell in sorted(by_cell, key=lambda c: (slot_index[c[1]], c[0])):
        market_id, slot_id = cell
        queue = [[sh.batch_id, sh.kg] for sh in sorted(by_cell[cell], key=lambda s: s.batch_id)]
        for truck_id in trucks_by_cell.get(cell, []):
            room = capacity[truck_id]
            manifest: list[TripLoad] = []
            while queue and room > 1e-9:
                take = min(room, queue[0][1])
                manifest.append(TripLoad(batch_id=queue[0][0], kg=round(take, 6)))
                room -= take
                queue[0][1] -= take
                if queue[0][1] <= 1e-9:
                    queue.pop(0)
            if manifest:
                load = round(sum(m.kg for m in manifest), 6)
                trips.append(Trip(truck_id=truck_id, slot_id=slot_id, market_id=market_id, load_kg=load, manifest=manifest))
        if queue:
            raise ValueError(f"cell {cell} has {sum(q[1] for q in queue):.0f} kg with no truck room")
    return trips


def assemble(
    scenario: Scenario,
    arm: Arm,
    basis: Basis,
    assignments: dict[str, tuple[str, str]],
    trucks_by_cell: dict[Cell, list[str]],
    discounts: dict[Cell, float],
    solver: SolverInfo | None = None,
    locked: set[str] | None = None,
) -> Plan:
    """`assignments` maps batch -> (market, slot). `discounts` maps (market, commodity) -> discount."""
    locked = locked or set()
    batches = {b.id: b for b in scenario.batches}
    shipments = [
        Shipment(
            batch_id=bid,
            market_id=m,
            slot_id=s,
            kg=batches[bid].kg,
            discount=discounts.get((m, batches[bid].commodity_id), 0.0),
            locked=bid in locked,
        )
        for bid, (m, s) in sorted(assignments.items())
    ]
    used_cells = sorted({(sh.market_id, batches[sh.batch_id].commodity_id) for sh in shipments})
    prices = [Price(market_id=m, commodity_id=c, discount=discounts.get((m, c), 0.0)) for m, c in used_cells]
    trips = pack_trips(scenario, shipments, trucks_by_cell)
    return Plan(
        scenario_id=scenario.id,
        arm=arm,
        basis=basis,
        shipments=shipments,
        trips=trips,
        prices=prices,
        held=sorted(b.id for b in scenario.batches if b.id not in assignments),
        infeasible=infeasible_batches(scenario),
        expected=expected(scenario, _Draft(trips, prices)),
        solver=solver,
    )


@dataclass(frozen=True)
class _Draft:
    trips: list[Trip]
    prices: list[Price]
