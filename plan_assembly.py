"""Turn an arm's decisions into a Plan: truck manifests, prices, held stock and forecast totals.

Every arm goes through `assemble`, so trips are packed and totals booked the same way for all of them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from plan_model import Arm, Basis, Plan, Price, Shipment, SolverInfo, Trip, TripLoad
from scenarios.model import Scenario
from sim.simulator import expected
from world import World, infeasible_batches

Cell = tuple[str, str]


@dataclass
class _Load:
    batch_id: str
    market_id: str
    kg: float


@dataclass(frozen=True)
class Leg:
    """Part (or all) of a batch leaving for a market at a slot."""

    batch_id: str
    market_id: str
    slot_id: str
    kg: float


def pack_trips(scenario: Scenario, shipments: list[Shipment]) -> list[Trip]:
    """Load each slot's shipments onto that slot's trucks, biggest truck first, keeping a market's
    stock together where it fits and splitting a batch across trucks when one fills up."""
    world = World(scenario, "point")
    by_slot: dict[str, list[Shipment]] = defaultdict(list)
    for sh in shipments:
        by_slot[sh.slot_id].append(sh)

    trips: list[Trip] = []
    for slot in scenario.slots:
        queue = [
            _Load(sh.batch_id, sh.market_id, sh.kg)
            for sh in sorted(by_slot.get(slot.id, []), key=lambda s: (s.market_id, s.batch_id))
        ]
        if not queue:
            continue
        fleet = sorted(
            (
                t
                for t in scenario.trucks
                if t.unavailable_from_slot is None or slot.index < t.unavailable_from_slot
            ),
            key=lambda t: (-t.capacity_kg, t.id),
        )
        for truck in fleet:
            room = truck.capacity_kg
            manifest: list[TripLoad] = []
            while queue and room > 1e-9:
                take = min(room, queue[0].kg)
                manifest.append(
                    TripLoad(batch_id=queue[0].batch_id, market_id=queue[0].market_id, kg=round(take, 6))
                )
                room -= take
                queue[0].kg -= take
                if queue[0].kg <= 1e-9:
                    queue.pop(0)
            if manifest:
                trips.append(
                    Trip(
                        truck_id=truck.id,
                        slot_id=slot.id,
                        load_kg=round(sum(m.kg for m in manifest), 6),
                        manifest=manifest,
                    )
                )
        if queue:
            left = sum(q.kg for q in queue)
            raise ValueError(
                f"slot {slot.id} has {left:.0f} kg more than {world.slot_capacity_kg(slot):.0f} kg of trucks"
            )
    return trips


def assemble(
    scenario: Scenario,
    arm: Arm,
    basis: Basis,
    legs: list[Leg],
    discounts: dict[Cell, float],
    solver: SolverInfo | None = None,
    locked: set[tuple[str, str, str]] | None = None,
) -> Plan:
    """`discounts` maps (market, commodity) to the discount the arm chose. Cells without one sell at list.
    `locked` holds the (batch, market, slot) legs the arm wasn't free to move."""
    locked = locked or set()
    commodity_of = {b.id: b.commodity_id for b in scenario.batches}
    slot_index = {s.id: s.index for s in scenario.slots}
    merged: dict[tuple[str, str, str], float] = defaultdict(float)
    for leg in legs:
        merged[(leg.batch_id, leg.market_id, leg.slot_id)] += leg.kg
    shipments = [
        Shipment(
            batch_id=bid,
            market_id=m,
            slot_id=s,
            kg=round(kg, 6),
            discount=discounts.get((m, commodity_of[bid]), 0.0),
            locked=(bid, m, s) in locked,
        )
        for (bid, m, s), kg in sorted(
            merged.items(), key=lambda kv: (kv[0][0], slot_index[kv[0][2]], kv[0][1])
        )
    ]
    used_cells = sorted({(sh.market_id, commodity_of[sh.batch_id]) for sh in shipments})
    prices = [Price(market_id=m, commodity_id=c, discount=discounts.get((m, c), 0.0)) for m, c in used_cells]
    trips = pack_trips(scenario, shipments)
    shipped = {sh.batch_id for sh in shipments}
    return Plan(
        scenario_id=scenario.id,
        arm=arm,
        basis=basis,
        shipments=shipments,
        trips=trips,
        prices=prices,
        held=sorted(b.id for b in scenario.batches if b.id not in shipped),
        infeasible=infeasible_batches(scenario),
        expected=expected(scenario, _Draft(trips, prices)),
        solver=solver,
    )


@dataclass(frozen=True)
class _Draft:
    trips: list[Trip]
    prices: list[Price]
