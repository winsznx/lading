"""Reference model: on 5 tiny scenarios, brute-force enumeration must match the MILP optimum.

The enumeration shares no code with the planner. It tries every batch -> (market, slot) choice and every
price level per cell, books each plan by hand and keeps the best feasible one. Batches are 1,000 kg and
trucks hold whole multiples of that, so splitting a batch across slots can't beat whole-batch choices
and the two searches cover the same plans.
"""

import itertools
from typing import Any

import pytest

from planner.milp import plan_lading
from scenarios.tiny import batch, market, scenario


def brute_force(s):
    margin = s.policy.safety_margin_h
    horizon = s.policy.horizon_h
    commodity = {c.id: c for c in s.commodities}
    options = []
    for b in s.batches:
        mine: list[Any] = [None]
        for m in s.markets:
            offer = next((o for o in m.offers if o.commodity_id == b.commodity_id), None)
            if offer is None:
                continue
            for sl in s.slots:
                if sl.depart_h + m.travel_h + m.handling_h <= b.shelf_life_h - margin:
                    mine.append((m, sl))
        options.append(mine)
    cells = sorted({(m.id, o.commodity_id) for m in s.markets for o in m.offers})
    levels = s.policy.discount_levels
    best = -float("inf")
    for choice in itertools.product(*options):
        load = {sl.id: 0.0 for sl in s.slots}
        for b, pick in zip(s.batches, choice, strict=True):
            if pick:
                load[pick[1].id] += b.kg
        if any(load[sl.id] > sum(t.capacity_kg for t in s.trucks) + 1e-9 for sl in s.slots):
            continue
        for prices in itertools.product(levels, repeat=len(cells)):
            price = dict(zip(cells, prices, strict=True))
            shipped = {cell: 0.0 for cell in cells}
            net = 0.0
            for b, pick in zip(s.batches, choice, strict=True):
                purchase = commodity[b.commodity_id].purchase_inr_per_kg
                if pick is None:
                    if b.shelf_life_h <= horizon:
                        net -= b.kg * purchase
                    continue
                m = pick[0]
                shipped[(m.id, b.commodity_id)] += b.kg
                net -= b.kg * (m.transport_inr_per_kg + m.handling_inr_per_kg)
            for (mid, cid), kg in shipped.items():
                if kg == 0:
                    continue
                m = next(mm for mm in s.markets if mm.id == mid)
                offer = next(o for o in m.offers if o.commodity_id == cid)
                d = price[(mid, cid)]
                sold = min(kg, offer.demand_kg * (1 + commodity[cid].elasticity * d))
                net += (
                    sold * offer.price_inr_per_kg * (1 - d) - (kg - sold) * commodity[cid].purchase_inr_per_kg
                )
            best = max(best, net)
    return best


CASES = {
    "expiry_vs_price": scenario(
        [batch("b1", "tomato", 1000, 9), batch("b2", "tomato", 1000, 30), batch("b3", "onion", 1000, 400)],
        [
            market("near", 3, {"tomato": (24.0, 1500), "onion": (18.0, 800)}),
            market("far", 9, {"tomato": (32.0, 1200), "onion": (25.0, 1500)}, transport=2.2),
        ],
        trucks=[1000],
        sid="ref-expiry",
    ),
    "capacity_choice": scenario(
        [
            batch("b1", "leafy_greens", 1000, 14),
            batch("b2", "leafy_greens", 1000, 8),
            batch("b3", "tomato", 1000, 40),
        ],
        [
            market("a", 2, {"leafy_greens": (30.0, 2500), "tomato": (22.0, 900)}),
            market("b", 5, {"tomato": (28.0, 1000)}),
        ],
        trucks=[1000],
        n_slots=3,
        sid="ref-capacity",
    ),
    "markdown_pays": scenario(
        [batch("b1", "tomato", 1000, 20), batch("b2", "tomato", 1000, 22), batch("b3", "tomato", 1000, 26)],
        [market("m1", 3, {"tomato": (25.0, 1600)}), market("m2", 6, {"tomato": (27.0, 700)}, transport=1.6)],
        trucks=[2000],
        discounts=[0.0, 0.3],
        sid="ref-markdown",
    ),
    "hold_beats_shipping": scenario(
        [batch("b1", "onion", 1000, 500), batch("b2", "onion", 1000, 500), batch("b3", "tomato", 1000, 12)],
        [market("m1", 4, {"onion": (17.0, 600), "tomato": (23.0, 1000)}, transport=1.4)],
        trucks=[2000],
        sid="ref-hold",
    ),
    "four_batches_three_slots": scenario(
        [
            batch("b1", "tomato", 1000, 11),
            batch("b2", "leafy_greens", 1000, 15),
            batch("b3", "tomato", 1000, 18),
            batch("b4", "leafy_greens", 1000, 26),
        ],
        [
            market("x", 3, {"tomato": (24.0, 1200), "leafy_greens": (29.0, 900)}),
            market("y", 8, {"tomato": (31.0, 1500), "leafy_greens": (36.0, 1500)}, transport=2.0),
        ],
        trucks=[1000],
        n_slots=3,
        sid="ref-four",
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_milp_matches_brute_force(name):
    s = CASES[name]
    plan = plan_lading(s, "lading-point", time_limit_s=30, mip_rel_gap=0.0)
    assert plan.solver is not None and plan.solver.status == "OPTIMAL"
    assert plan.solver.objective_inr == pytest.approx(brute_force(s), abs=0.01)
    assert plan.expected.net_inr == pytest.approx(plan.solver.objective_inr, abs=0.01)
