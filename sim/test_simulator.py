import pytest

from baselines.fefo import plan_fefo
from plan_assembly import assemble
from scenarios.scenario_gen import generate
from scenarios.tiny import batch, market, scenario
from sim.draws import Realization, forecast, realize
from sim.simulator import execute, execute_many


def world(s, shelf=None, travel=None, demand=None, lost=None):
    base = forecast(s)
    return Realization(
        label="hand",
        shelf_h={**base.shelf_h, **(shelf or {})},
        travel_h={**base.travel_h, **(travel or {})},
        demand_kg={**base.demand_kg, **(demand or {})},
        elasticity=base.elasticity,
        truck_lost_from_slot=lost or {},
    )


@pytest.fixture
def one_lane():
    s = scenario(
        [batch("b1", "tomato", 1000, 10), batch("b2", "onion", 800, 500)],
        [market("near", 3, {"tomato": (26.0, 1000), "onion": (20.0, 1000)}, transport=0.9, handling=0.5)],
        trucks=[5000],
    )
    plan = assemble(s, "fefo", "point", {"b1": ("near", "s0")}, {("near", "s0"): ["t1"]}, {})
    return s, plan


def test_fresh_arrival_sells_up_to_realized_demand(one_lane):
    s, plan = one_lane
    out = execute(s, plan, world(s, demand={("near", "tomato"): 600.0}))
    assert out.sold_kg == pytest.approx(600)
    assert out.unsold_kg == pytest.approx(400)
    assert out.carry_over_kg == pytest.approx(800)
    assert out.spoiled_kg == pytest.approx(400)
    # 600 x 26 - 1,000 x (0.9 + 0.5) - 400 x 14
    assert out.costs.net_inr == pytest.approx(15_600 - 1_400 - 5_600)
    # Filled: tomato 600 of 600, onion 0 of 1,000.
    assert out.demand_filled_pct == pytest.approx(100 * 600 / 1600)


def test_delay_past_expiry_spoils_in_transit(one_lane):
    s, plan = one_lane
    out = execute(s, plan, world(s, travel={("near", "s0"): 9.5}))
    # On sale at 0 + 9.5 + 1 = 10.5 h, shelf life 10 h.
    assert out.expired_in_transit_kg == pytest.approx(1000)
    assert out.sold_kg == 0
    assert out.costs.net_inr == pytest.approx(-1_400 - 14_000)


def test_shorter_realized_shelf_life_spoils_in_transit(one_lane):
    s, plan = one_lane
    out = execute(s, plan, world(s, shelf={"b1": 3.5}))
    assert out.expired_in_transit_kg == pytest.approx(1000)


def test_lost_truck_leaves_stock_at_the_hub(one_lane):
    s, plan = one_lane
    out = execute(s, plan, world(s, lost={"t1": 0}))
    assert out.cancelled_kg == pytest.approx(1000)
    assert out.hub_spoiled_kg == pytest.approx(1000)
    assert out.costs.transport_inr == 0
    assert out.costs.net_inr == pytest.approx(-14_000)


def test_first_on_sale_sells_first():
    s = scenario(
        [batch("b1", "tomato", 1000, 30), batch("b2", "tomato", 1000, 30)],
        [market("near", 3, {"tomato": (26.0, 1000)})],
        trucks=[1000, 1000],
    )
    plan = assemble(
        s, "fefo", "point", {"b1": ("near", "s1"), "b2": ("near", "s0")},
        {("near", "s0"): ["t1"], ("near", "s1"): ["t2"]}, {},
    )
    out = execute(s, plan, forecast(s))
    assert out.sold_kg == pytest.approx(1000)
    assert out.unsold_kg == pytest.approx(1000)


def test_draws_are_deterministic_and_plan_independent():
    s = generate(5)
    assert realize(s, 3) == realize(s, 3)
    assert realize(s, 3) != realize(s, 4)
    plan = plan_fefo(s)
    assert execute_many(s, plan, draws=5) == execute_many(s, plan, draws=5)


def test_forecast_execution_matches_the_plan_claim():
    s = generate(6)
    plan = plan_fefo(s)
    out = execute(s, plan, forecast(s))
    assert out.costs.net_inr == pytest.approx(plan.expected.net_inr, abs=0.01)
