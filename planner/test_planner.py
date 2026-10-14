import json

import pytest

from baselines.test_baselines import far_market_trap
from errors import LadingError, State
from planner.decisions import build_decisions
from planner.milp import plan_lading
from scenarios.model import Scenario
from scenarios.scenario_gen import generate
from validate.validator import validate


def as_json(model):
    return json.loads(model.model_dump_json())


@pytest.fixture(scope="module")
def day():
    return generate(2)


def test_point_objective_equals_forecast_net(day):
    plan = plan_lading(day, "lading-point", time_limit_s=60)
    assert plan.expected.net_inr == pytest.approx(plan.solver.objective_inr, abs=0.01)


@pytest.mark.parametrize("arm", ["lading-point", "lading-robust", "ablation-no-discount"])
def test_every_hard_arm_passes_the_validator(day, arm):
    plan = plan_lading(day, arm, time_limit_s=60)
    assert validate(as_json(day), as_json(plan))["status"] == "PASS"


def test_no_discount_ablation_never_discounts(day):
    plan = plan_lading(day, "ablation-no-discount", time_limit_s=60)
    assert all(p.discount == 0 for p in plan.prices)


def test_refuses_far_market_and_says_why():
    s = far_market_trap()
    plan = plan_lading(s, "lading-robust")
    decision = next(d for d in build_decisions(s, plan) if d.batch_id == "b1")
    assert decision.market_id == "near"
    far = next(a for a in decision.alternatives if a.market_id == "far")
    assert far.code == "EXPIRED_ON_ARRIVAL"
    assert far.sale_h > far.limit_h


def test_execution_shocks_never_reach_the_planner(day):
    raw = as_json(day)
    raw["execution"] = {
        "route_delay": {"market_id": day.markets[0].id, "extra_h": 12},
        "demand_shock": {"market_id": day.markets[1].id, "factor": 0.1},
        "truck_loss": {"truck_id": day.trucks[0].id, "from_slot": 0},
        "elasticity_factor": 0.2,
    }
    shocked = Scenario.model_validate(raw)
    clean, blind = plan_lading(day, "lading-robust", time_limit_s=60), plan_lading(shocked, "lading-robust", time_limit_s=60)
    assert clean.shipments == blind.shipments and clean.prices == blind.prices


def test_veto_moves_the_batch(day):
    plan = plan_lading(day, "lading-robust", time_limit_s=60)
    target = plan.shipments[0]
    raw = as_json(day)
    raw["controls"] = {"locks": [], "vetoes": [{"batch_id": target.batch_id, "market_id": target.market_id}]}
    vetoed = plan_lading(Scenario.model_validate(raw), "lading-robust", time_limit_s=60)
    assert all(not (s.batch_id == target.batch_id and s.market_id == target.market_id) for s in vetoed.shipments)


def test_lock_is_honoured_and_marked(day):
    plan = plan_lading(day, "lading-robust", time_limit_s=60)
    held = next(b for b in day.batches if b.id in plan.held and b.id not in plan.infeasible)
    world_market = next(
        m for m in day.markets
        if day.offer(m.id, held.commodity_id) and m.travel_h + m.handling_h <= held.shelf_life_h - day.policy.safety_margin_h
    )
    raw = as_json(day)
    raw["controls"] = {"locks": [{"batch_id": held.id, "market_id": world_market.id, "slot_id": "s0"}], "vetoes": []}
    locked = plan_lading(Scenario.model_validate(raw), "lading-robust", time_limit_s=60)
    leg = next(s for s in locked.shipments if s.batch_id == held.id)
    assert (leg.market_id, leg.slot_id, leg.locked) == (world_market.id, "s0", True)


def test_impossible_lock_is_a_named_error():
    s = far_market_trap()
    raw = as_json(s)
    raw["controls"] = {"locks": [{"batch_id": "b1", "market_id": "far", "slot_id": "s0"}], "vetoes": []}
    with pytest.raises(LadingError) as exc:
        plan_lading(Scenario.model_validate(raw), "lading-robust")
    assert exc.value.state is State.LOCK_INFEASIBLE


def test_infeasible_batches_are_flagged_and_counted_as_spoiled():
    s = generate(4, "infeasible")
    plan = plan_lading(s, "lading-robust", time_limit_s=60)
    assert len(plan.infeasible) == 3
    assert set(plan.infeasible) <= set(plan.held)
    statuses = {d.batch_id: d.hold_code for d in build_decisions(s, plan)}
    assert all(statuses[b] == "INFEASIBLE_DEMAND" for b in plan.infeasible)
