"""Decision objects: for every batch, what the plan chose and why each alternative lost.

Built from the solved plan and the same planning view (`World`) the solver used, so a reason never
cites a number the planner didn't plan on. The reason engine in `explain/` turns these into sentences.

Per-batch money is a local estimate: the batch's own sales at its market's price, minus its freight and
handling, minus the purchase value of its unsold kg. Demand in a cell is shared first-come first-served
by time on sale, the same rule the simulator uses.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

import cost_model
from plan_model import Plan
from scenarios.model import Batch, Market, Scenario
from world import World, infeasible_batches

AltCode = Literal[
    "EXPIRED_ON_ARRIVAL", "DEADLINE", "VETOED", "TRUCK_FULL", "DEMAND_MET", "LOWER_NET", "PLAN_TRADEOFF", "HOLD"
]
HoldCode = Literal["INFEASIBLE_DEMAND", "TOO_RISKY", "CARRY_OVER", "NOT_WORTH_SHIPPING", "NO_ROOM"]


class LegView(BaseModel):
    slot_id: str
    slot_label: str
    kg: float
    sale_h: float
    margin_h: float


class Alternative(BaseModel):
    market_id: str | None
    market_name: str
    code: AltCode
    sale_h: float | None = None
    limit_h: float | None = None
    deadline_h: float | None = None
    last_slot_label: str | None = None
    demand_left_kg: float | None = None
    net_inr: float | None = None
    delta_inr: float | None = None


class Decision(BaseModel):
    batch_id: str
    commodity_id: str
    commodity_name: str
    kg: float
    origin: str
    shelf_h: float
    plan_shelf_h: float
    basis: str
    status: Literal["assigned", "held", "infeasible"]
    market_id: str | None
    market_name: str | None
    discount: float | None
    legs: list[LegView]
    net_inr: float
    hold_code: HoldCode | None
    locked: bool
    alternatives: list[Alternative]


def _sold_by_batch(scenario: Scenario, plan: Plan, world: World) -> dict[str, float]:
    markets = {m.id: m for m in scenario.markets}
    slots = {s.id: s for s in scenario.slots}
    commodity = {b.id: b.commodity_id for b in scenario.batches}
    price = {(p.market_id, p.commodity_id): p.discount for p in plan.prices}
    arriving: dict[tuple[str, str], list[tuple[float, str, float]]] = defaultdict(list)
    for sh in plan.shipments:
        m, s = markets[sh.market_id], slots[sh.slot_id]
        arriving[(m.id, commodity[sh.batch_id])].append((world.sale_h(m, s), sh.batch_id, sh.kg))
    sold: dict[str, float] = defaultdict(float)
    for cell, rows in arriving.items():
        offer = scenario.offer(*cell)
        assert offer is not None
        room = cost_model.demand_cap_kg(offer.demand_kg, scenario.commodity(cell[1]).elasticity, price.get(cell, 0.0))
        for _, bid, kg in sorted(rows):
            take = min(kg, max(room, 0.0))
            sold[bid] += take
            room -= take
    return sold


def _local_net(scenario: Scenario, b: Batch, m: Market, sold_kg: float, discount: float) -> float:
    purchase = scenario.commodity(b.commodity_id).purchase_inr_per_kg
    unit_sale = cost_model.sale_inr_per_kg(scenario.list_price(m.id, b.commodity_id), discount)
    unit_route = cost_model.route_inr_per_kg(m.transport_inr_per_kg, m.handling_inr_per_kg)
    return sold_kg * unit_sale - b.kg * unit_route - (b.kg - sold_kg) * cost_model.spoilage_inr_per_kg(purchase)


def build_decisions(scenario: Scenario, plan: Plan) -> list[Decision]:
    world = World(scenario, plan.basis if plan.basis != "none" else "point")
    margin = scenario.policy.safety_margin_h
    slots = {s.id: s for s in scenario.slots}
    markets = {m.id: m for m in scenario.markets}
    infeasible = set(infeasible_batches(scenario))
    vetoed = {(v.batch_id, v.market_id) for v in scenario.controls.vetoes}
    locked = {lk.batch_id for lk in scenario.controls.locks}
    price = {(p.market_id, p.commodity_id): p.discount for p in plan.prices}
    sold = _sold_by_batch(scenario, plan, world)

    shipments_of: dict[str, list] = defaultdict(list)
    for sh in plan.shipments:
        shipments_of[sh.batch_id].append(sh)
    shipped_in_cell: dict[tuple[str, str], float] = defaultdict(float)
    for sh in plan.shipments:
        shipped_in_cell[(sh.market_id, scenario.batch(sh.batch_id).commodity_id)] += sh.kg
    load = {s.id: 0.0 for s in scenario.slots}
    for sh in plan.shipments:
        load[sh.slot_id] += sh.kg

    decisions = []
    for b in scenario.batches:
        mine = shipments_of.get(b.id, [])
        purchase = scenario.commodity(b.commodity_id).purchase_inr_per_kg
        hold_value = -b.kg * cost_model.spoilage_inr_per_kg(purchase) if world.expires_in_horizon(b) else 0.0
        chosen_market = markets[mine[0].market_id] if mine else None
        discount = price.get((chosen_market.id, b.commodity_id), 0.0) if chosen_market else None
        own_net = (
            _local_net(scenario, b, chosen_market, sold.get(b.id, 0.0), discount or 0.0) if chosen_market else hold_value
        )
        legs = [
            LegView(
                slot_id=sh.slot_id,
                slot_label=slots[sh.slot_id].label,
                kg=round(sh.kg, 2),
                sale_h=round(world.sale_h(markets[sh.market_id], slots[sh.slot_id]), 2),
                margin_h=round(world.shelf_h(b) - world.sale_h(markets[sh.market_id], slots[sh.slot_id]), 2),
            )
            for sh in mine
        ]

        alternatives: list[Alternative] = []
        for m in scenario.markets:
            if (chosen_market and m.id == chosen_market.id) or not world.sells(b, m):
                continue
            first = world.open_slots[0] if world.open_slots else None
            if (b.id, m.id) in vetoed:
                alternatives.append(Alternative(market_id=m.id, market_name=m.name, code="VETOED"))
                continue
            fresh = world.fresh_slots(b, m)
            if not fresh:
                sale = world.sale_h(m, first) if first else None
                limit = world.shelf_h(b) - margin
                late_for_order = m.deliver_by_h is not None and sale is not None and sale > m.deliver_by_h and sale <= limit
                alternatives.append(
                    Alternative(
                        market_id=m.id,
                        market_name=m.name,
                        code="DEADLINE" if late_for_order else "EXPIRED_ON_ARRIVAL",
                        sale_h=round(sale, 2) if sale is not None else None,
                        limit_h=round(limit, 2),
                        deadline_h=m.deliver_by_h,
                    )
                )
                continue
            cell = (m.id, b.commodity_id)
            d = price.get(cell, 0.0)
            offer = scenario.offer(*cell)
            assert offer is not None
            left = cost_model.demand_cap_kg(offer.demand_kg, scenario.commodity(b.commodity_id).elasticity, d)
            left -= shipped_in_cell.get(cell, 0.0)
            if left <= 1e-6:
                alternatives.append(
                    Alternative(market_id=m.id, market_name=m.name, code="DEMAND_MET", demand_left_kg=0.0)
                )
                continue
            own_room = sum(sh.kg for sh in mine if slots[sh.slot_id].index <= fresh[-1].index)
            room = sum(world.slot_capacity_kg(s) - load[s.id] for s in fresh) + own_room
            if room < b.kg - 1e-6:
                alternatives.append(
                    Alternative(
                        market_id=m.id, market_name=m.name, code="TRUCK_FULL", last_slot_label=fresh[-1].label,
                        demand_left_kg=round(left, 1),
                    )
                )
                continue
            alt_net = _local_net(scenario, b, m, min(b.kg, left), d)
            delta = own_net - alt_net
            alternatives.append(
                Alternative(
                    market_id=m.id,
                    market_name=m.name,
                    code="LOWER_NET" if delta >= 0 else "PLAN_TRADEOFF",
                    sale_h=round(world.sale_h(m, fresh[0]), 2),
                    demand_left_kg=round(left, 1),
                    net_inr=round(alt_net, 2),
                    delta_inr=round(delta, 2),
                )
            )
        if chosen_market:
            alternatives.append(
                Alternative(
                    market_id=None, market_name="Hold at hub", code="HOLD", net_inr=round(hold_value, 2),
                    delta_inr=round(own_net - hold_value, 2),
                )
            )

        hold_code: HoldCode | None = None
        status: Literal["assigned", "held", "infeasible"] = "assigned"
        if not chosen_market:
            status = "held"
            fresh_anywhere = any(world.fresh_slots(b, m) for m in scenario.markets if world.sells(b, m))
            if b.id in infeasible:
                status, hold_code = "infeasible", "INFEASIBLE_DEMAND"
            elif not fresh_anywhere:
                hold_code = "TOO_RISKY"
            elif not world.expires_in_horizon(b):
                hold_code = "CARRY_OVER"
            elif all(a.code in {"TRUCK_FULL", "DEMAND_MET", "VETOED", "EXPIRED_ON_ARRIVAL", "DEADLINE"} for a in alternatives):
                hold_code = "NO_ROOM"
            else:
                hold_code = "NOT_WORTH_SHIPPING"

        decisions.append(
            Decision(
                batch_id=b.id,
                commodity_id=b.commodity_id,
                commodity_name=scenario.commodity(b.commodity_id).name,
                kg=b.kg,
                origin=b.origin,
                shelf_h=b.shelf_life_h,
                plan_shelf_h=round(world.shelf_h(b), 2),
                basis=world.basis,
                status=status,
                market_id=chosen_market.id if chosen_market else None,
                market_name=chosen_market.name if chosen_market else None,
                discount=discount,
                legs=legs,
                net_inr=round(own_net, 2),
                hold_code=hold_code,
                locked=b.id in locked,
                alternatives=alternatives,
            )
        )
    return decisions
