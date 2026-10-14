"""Execution simulator. Plays a plan against a realized world and books the outcome.

Plans are made on forecasts. Here they meet realized shelf life, travel time and demand:

* a trip on a truck that broke down doesn't leave; its stock stays at the hub;
* stock on sale after its realized expiry, or after an order deadline, is spoiled;
* fresh stock sells first-come first-served up to realized demand at the plan's price, the rest is
  unsold and spoiled (a mandi doesn't hold consignment for the hub);
* stock left at the hub spoils if it expires inside the horizon, otherwise it carries over.

Money is booked only through `cost_model`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

import cost_model
from plan_model import Expected, Price, Trip
from scenarios.model import Scenario
from sim.draws import Realization, forecast, realize

DEFAULT_DRAWS = 30


class Executable(Protocol):
    """What execution needs from a plan: the trucks that leave and the prices on sale."""

    @property
    def trips(self) -> Sequence[Trip]: ...

    @property
    def prices(self) -> Sequence[Price]: ...


@dataclass(frozen=True)
class Outcome:
    spoiled_kg: float
    expired_in_transit_kg: float
    unsold_kg: float
    hub_spoiled_kg: float
    carry_over_kg: float
    sold_kg: float
    shipped_kg: float
    cancelled_kg: float
    demand_kg: float
    demand_filled_kg: float
    demand_filled_pct: float
    unmet_demand_kg: float
    costs: cost_model.CostBreakdown


def execute(scenario: Scenario, plan: Executable, real: Realization) -> Outcome:
    slots = {s.id: s for s in scenario.slots}
    markets = {m.id: m for m in scenario.markets}
    batches = {b.id: b for b in scenario.batches}
    commodities = {c.id: c for c in scenario.commodities}
    price_of = {(p.market_id, p.commodity_id): p.discount for p in plan.prices}

    on_road: dict[str, float] = defaultdict(float)
    arrivals: dict[tuple[str, str], list[tuple[float, str, float]]] = defaultdict(list)
    hauls: list[cost_model.Haul] = []
    losses: list[cost_model.Loss] = []
    expired = cancelled = unsold_total = 0.0

    for trip in plan.trips:
        slot = slots[trip.slot_id]
        lost_from = real.truck_lost_from_slot.get(trip.truck_id)
        if lost_from is not None and slot.index >= lost_from:
            cancelled += sum(load.kg for load in trip.manifest)
            continue
        for load in trip.manifest:
            batch, market = batches[load.batch_id], markets[load.market_id]
            sale_h = slot.depart_h + real.travel_h[(market.id, slot.id)] + market.handling_h
            on_road[batch.id] += load.kg
            hauls.append(cost_model.Haul(load.kg, market.transport_inr_per_kg, market.handling_inr_per_kg))
            purchase = commodities[batch.commodity_id].purchase_inr_per_kg
            if sale_h > real.shelf_h[batch.id]:
                expired += load.kg
                losses.append(cost_model.Loss(load.kg, purchase))
            elif market.deliver_by_h is not None and sale_h > market.deliver_by_h:
                unsold_total += load.kg
                losses.append(cost_model.Loss(load.kg, purchase))
            else:
                arrivals[(market.id, batch.commodity_id)].append((sale_h, batch.id, load.kg))

    sales: list[cost_model.Sale] = []
    sold_in_cell: dict[tuple[str, str], float] = defaultdict(float)
    for cell in sorted(arrivals):
        market_id, commodity_id = cell
        offer = scenario.offer(market_id, commodity_id)
        price = offer.price_inr_per_kg if offer else 0.0
        discount = price_of.get(cell, 0.0)
        base = real.demand_kg.get(cell, 0.0)
        room = cost_model.demand_cap_kg(base, real.elasticity[commodity_id], discount)
        purchase = commodities[commodity_id].purchase_inr_per_kg
        for _, _, kg in sorted(arrivals[cell]):
            sold = min(kg, max(room, 0.0))
            room -= sold
            if sold > 0:
                sales.append(cost_model.Sale(sold, price, discount))
                sold_in_cell[cell] += sold
            if kg - sold > 1e-9:
                unsold_total += kg - sold
                losses.append(cost_model.Loss(kg - sold, purchase))

    hub_spoiled = carry_over = 0.0
    for b in scenario.batches:
        left = b.kg - on_road.get(b.id, 0.0)
        if left <= 1e-9:
            continue
        if real.shelf_h[b.id] <= scenario.policy.horizon_h:
            hub_spoiled += left
            losses.append(cost_model.Loss(left, commodities[b.commodity_id].purchase_inr_per_kg))
        else:
            carry_over += left

    demand_total = sum(real.demand_kg.values())
    filled = sum(min(sold_in_cell.get(cell, 0.0), base) for cell, base in real.demand_kg.items())
    sold_total = sum(sold_in_cell.values())
    costs = cost_model.breakdown(sales, hauls, losses)
    return Outcome(
        spoiled_kg=expired + unsold_total + hub_spoiled,
        expired_in_transit_kg=expired,
        unsold_kg=unsold_total,
        hub_spoiled_kg=hub_spoiled,
        carry_over_kg=carry_over,
        sold_kg=sold_total,
        shipped_kg=sum(on_road.values()),
        cancelled_kg=cancelled,
        demand_kg=demand_total,
        demand_filled_kg=filled,
        demand_filled_pct=100.0 * filled / demand_total if demand_total > 0 else 100.0,
        unmet_demand_kg=demand_total - filled,
        costs=costs,
    )


def expected(scenario: Scenario, plan: Executable) -> Expected:
    out = execute(scenario, plan, forecast(scenario))
    c = out.costs
    return Expected(
        revenue_inr=round(c.revenue_inr, 2),
        discount_given_up_inr=round(c.discount_given_up_inr, 2),
        transport_inr=round(c.transport_inr, 2),
        handling_inr=round(c.handling_inr, 2),
        spoilage_inr=round(c.spoilage_inr, 2),
        net_inr=round(c.net_inr, 2),
        sold_kg=round(out.sold_kg, 2),
        unsold_kg=round(out.unsold_kg, 2),
        expired_in_transit_kg=round(out.expired_in_transit_kg, 2),
        hub_spoiled_kg=round(out.hub_spoiled_kg, 2),
        carry_over_kg=round(out.carry_over_kg, 2),
    )


METRICS = (
    "spoiled_kg",
    "expired_in_transit_kg",
    "unsold_kg",
    "hub_spoiled_kg",
    "carry_over_kg",
    "sold_kg",
    "shipped_kg",
    "cancelled_kg",
    "demand_kg",
    "demand_filled_pct",
    "unmet_demand_kg",
)
COST_METRICS = ("revenue_inr", "discount_given_up_inr", "transport_inr", "handling_inr", "spoilage_inr", "net_inr")


def execute_many(scenario: Scenario, plan: Executable, draws: int = DEFAULT_DRAWS) -> dict[str, float]:
    """Mean outcome over `draws` realized days, plus the P10 and P90 of net INR across them."""
    outcomes = [execute(scenario, plan, realize(scenario, d)) for d in range(draws)]
    summary: dict[str, float] = {}
    for key in METRICS:
        summary[key] = round(float(np.mean([getattr(o, key) for o in outcomes])), 2)
    for key in COST_METRICS:
        summary[key] = round(float(np.mean([getattr(o.costs, key) for o in outcomes])), 2)
    nets = [o.costs.net_inr for o in outcomes]
    summary["net_inr_p10"] = round(float(np.percentile(nets, 10)), 2)
    summary["net_inr_p90"] = round(float(np.percentile(nets, 90)), 2)
    summary["draws"] = float(draws)
    return summary


def outcome_dict(o: Outcome) -> dict[str, object]:
    d = asdict(o)
    d["costs"] = o.costs.as_dict()
    return d
