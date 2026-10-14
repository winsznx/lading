"""Three hand-checked scenarios for each baseline. Expected values are worked out in the comments."""

import pytest

from baselines.fefo import plan_fefo
from baselines.fifo import plan_fifo
from scenarios.tiny import batch, market, scenario


def assignment(plan):
    out: dict[str, tuple[str, str]] = {}
    for s in plan.shipments:
        out.setdefault(s.batch_id, (s.market_id, s.slot_id))
    return out


def far_market_trap():
    # b1 tomato, 10 h of shelf life. near: on sale at 0 + 3 + 1 = 4 h <= 10 - 2 margin. far pays more but
    # is on sale at 0 + 10 + 1 = 11 h, after expiry.
    return scenario(
        [batch("b1", "tomato", 1000, 10, arrived_h_ago=20)],
        [
            market("near", 3, {"tomato": (26.0, 2000)}, transport=0.9),
            market("far", 10, {"tomato": (34.0, 2000)}, transport=2.0),
        ],
        trucks=[5000],
    )


def one_truck_two_batches():
    # One 1 t truck and one slot. b1 leafy greens expires at 9 h; b2 onion has 500 h left but arrived first.
    return scenario(
        [
            batch("b1", "leafy_greens", 1000, 9, arrived_h_ago=0),
            batch("b2", "onion", 1000, 500, arrived_h_ago=30),
        ],
        [market("near", 3, {"leafy_greens": (30.0, 1000), "onion": (22.0, 1000)})],
        trucks=[1000],
        n_slots=1,
    )


def short_demand_needs_markdown():
    # 2 t of tomato, 1.2 t of demand at 25/kg, elasticity 1.5, freight + handling 1.5/kg.
    return scenario(
        [batch("b1", "tomato", 1000, 20), batch("b2", "tomato", 1000, 30)],
        [market("near", 3, {"tomato": (25.0, 1200)})],
        trucks=[5000],
        discounts=[0.0, 0.1, 0.2, 0.3],
    )


class TestFEFO:
    def test_refuses_market_it_cannot_reach_fresh(self):
        plan = plan_fefo(far_market_trap())
        assert assignment(plan) == {"b1": ("near", "s0")}
        # 1,000 kg x 26 - 1,000 x (0.9 + 0.5)
        assert plan.expected.net_inr == pytest.approx(24_600)
        assert plan.expected.expired_in_transit_kg == 0

    def test_shortest_life_gets_the_only_truck(self):
        plan = plan_fefo(one_truck_two_batches())
        assert assignment(plan) == {"b1": ("near", "s0")}
        assert plan.held == ["b2"]
        assert plan.expected.hub_spoiled_kg == 0
        assert plan.expected.carry_over_kg == 1000

    def test_marks_down_when_stock_would_go_unsold(self):
        plan = plan_fefo(short_demand_needs_markdown())
        assert assignment(plan) == {"b1": ("near", "s0"), "b2": ("near", "s0")}
        assert [(p.market_id, p.commodity_id, p.discount) for p in plan.prices] == [("near", "tomato", 0.3)]
        # Demand at 30% off = 1,200 x 1.45 = 1,740 kg. Revenue 1,740 x 17.5 = 30,450.
        # Freight + handling 2,000 x 1.5 = 3,000. Unsold 260 kg x 14 = 3,640. Net 23,810.
        # Without the markdown: 1,200 x 25 - 3,000 - 800 x 14 = 15,800.
        assert plan.expected.sold_kg == pytest.approx(1740)
        assert plan.expected.net_inr == pytest.approx(23_810)


class TestFIFO:
    def test_falls_for_the_far_market(self):
        plan = plan_fifo(far_market_trap())
        assert assignment(plan) == {"b1": ("far", "s0")}
        assert plan.expected.expired_in_transit_kg == 1000

    def test_ships_oldest_arrival_first_and_loses_the_greens(self):
        plan = plan_fifo(one_truck_two_batches())
        assert assignment(plan) == {"b2": ("near", "s0")}
        assert plan.expected.hub_spoiled_kg == 1000

    def test_never_discounts(self):
        plan = plan_fifo(short_demand_needs_markdown())
        assert all(p.discount == 0 for p in plan.prices)
        assert plan.expected.sold_kg == pytest.approx(1200)
