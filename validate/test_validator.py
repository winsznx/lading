import copy
import json

import pytest

from baselines.fefo import plan_fefo
from baselines.fifo import plan_fifo
from baselines.test_baselines import far_market_trap
from scenarios.scenario_gen import generate
from validate.validator import validate


def as_json(model):
    return json.loads(model.model_dump_json())


@pytest.fixture(scope="module")
def case():
    scenario = generate(7)
    return as_json(scenario), as_json(plan_fefo(scenario))


def test_fefo_plan_passes(case):
    scenario, plan = case
    report = validate(scenario, plan)
    assert report["status"] == "PASS", report["violations"]
    assert report["checks"]["shelf_life"] == len(plan["shipments"])


@pytest.mark.parametrize(
    ("tamper", "check"),
    [
        (
            lambda p: p["trips"][0]["manifest"][0].__setitem__("kg", p["trips"][0]["manifest"][0]["kg"] + 50),
            "trip.load",
        ),
        (lambda p: p["shipments"][0].__setitem__("kg", p["shipments"][0]["kg"] + 50), "stock"),
        (lambda p: p["expected"].__setitem__("net_inr", p["expected"]["net_inr"] + 500), "total.net_inr"),
        (lambda p: p["shipments"][0].__setitem__("discount", 0.2), "price.consistent"),
        (lambda p: p["prices"][0].__setitem__("discount", 0.15), "price.level"),
    ],
)
def test_tampering_with_one_value_fails(case, tamper, check):
    scenario, plan = case
    bad = copy.deepcopy(plan)
    tamper(bad)
    report = validate(scenario, bad)
    assert report["status"] == "FAIL"
    assert check in {v["check"] for v in report["violations"]}


def test_overloaded_truck_fails(case):
    scenario, plan = case
    bad = copy.deepcopy(plan)
    trip = bad["trips"][0]
    cap = next(t["capacity_kg"] for t in scenario["trucks"] if t["id"] == trip["truck_id"])
    extra = cap - trip["load_kg"] + 100
    trip["manifest"][0]["kg"] += extra
    trip["load_kg"] += extra
    report = validate(scenario, bad)
    assert "truck.capacity" in {v["check"] for v in report["violations"]}


def test_truck_used_twice_in_a_slot_fails(case):
    scenario, plan = case
    bad = copy.deepcopy(plan)
    clash = copy.deepcopy(bad["trips"][0])
    clash["manifest"] = []
    clash["load_kg"] = 0
    bad["trips"].append(clash)
    report = validate(scenario, bad)
    assert "truck.once_per_slot" in {v["check"] for v in report["violations"]}


def test_lading_plan_passes():
    from planner.milp import plan_lading

    scenario = generate(3)
    report = validate(as_json(scenario), as_json(plan_lading(scenario, "lading-robust", time_limit_s=60)))
    assert report["status"] == "PASS", report["violations"]


def test_fifo_expiry_violation_is_caught():
    scenario = far_market_trap()
    report = validate(as_json(scenario), as_json(plan_fifo(scenario)))
    assert report["status"] == "FAIL"
    assert [v["check"] for v in report["violations"]] == ["shelf_life"]


def test_negative_kg_phantom_line_fails(case):
    scenario, plan = case
    bad = copy.deepcopy(plan)
    sh = copy.deepcopy(bad["shipments"][0])
    sh["kg"] = -300
    bad["shipments"].append(sh)
    trip = copy.deepcopy(bad["trips"][0])
    trip["manifest"] = [{"batch_id": sh["batch_id"], "market_id": sh["market_id"], "kg": -300}]
    trip["load_kg"] = -300
    bad["trips"].append(trip)
    assert "kg.positive" in {v["check"] for v in validate(scenario, bad)["violations"]}


def test_shipping_a_vetoed_pair_fails(case):
    scenario, plan = case
    sh = plan["shipments"][0]
    vetoed = copy.deepcopy(scenario)
    vetoed["controls"]["vetoes"] = [{"batch_id": sh["batch_id"], "market_id": sh["market_id"]}]
    assert "veto" in {v["check"] for v in validate(vetoed, plan)["violations"]}


def test_breaking_a_lock_fails(case):
    scenario, plan = case
    sh = plan["shipments"][0]
    other = next(s for s in scenario["slots"] if s["id"] != sh["slot_id"])
    locked = copy.deepcopy(scenario)
    locked["controls"]["locks"] = [
        {"batch_id": sh["batch_id"], "market_id": sh["market_id"], "slot_id": other["id"]}
    ]
    assert "lock" in {v["check"] for v in validate(locked, plan)["violations"]}
