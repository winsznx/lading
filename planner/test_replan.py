import json

import pytest

from planner.milp import plan_lading
from planner.replan import Disruption, NewOrder, apply, replan
from scenarios.scenario_gen import generate
from scenarios.tiny import batch, market, scenario
from validate.validator import validate


def two_markets():
    # Two tomato batches with 12 h left. near (3 h) and mid (5 h) both reach them fresh.
    return scenario(
        [batch("b1", "tomato", 1000, 12), batch("b2", "tomato", 1000, 30), batch("b3", "tomato", 1000, 40)],
        [
            market("near", 3, {"tomato": (24.0, 1500)}),
            market("mid", 5, {"tomato": (30.0, 2000)}, transport=1.2),
        ],
        trucks=[1000, 1000],
        n_slots=3,
    )


def test_noop_replan_changes_nothing_and_keeps_what_left():
    s = generate(1003)
    plan = plan_lading(s, "lading-point")
    first = next(sh for sh in plan.shipments if sh.slot_id == "s0")
    result = replan(
        s,
        plan,
        Disruption(
            kind="demand_spike",
            label="no-op",
            at_slot=1,
            market_id=first.market_id,
            commodity_id=s.batch(first.batch_id).commodity_id,
            factor=1.0,
        ),
    )
    assert result.changes == []
    left = [sh for sh in result.plan.shipments if sh.slot_id == "s0"]
    assert [(sh.batch_id, sh.kg, sh.locked) for sh in left] == [
        (sh.batch_id, sh.kg, True) for sh in plan.shipments if sh.slot_id == "s0"
    ]


def test_route_delay_moves_a_batch_that_no_longer_arrives_fresh():
    s = two_markets()
    plan = plan_lading(s, "lading-point")
    b1 = next(sh for sh in plan.shipments if sh.batch_id == "b1")
    assert (b1.market_id, b1.slot_id) == ("mid", "s0")
    delayed = replan(
        s,
        plan,
        Disruption(kind="route_delay", label="Delay to mid +6h", at_slot=0, market_id="mid", extra_h=6),
    )
    change = next(c for c in delayed.changes if c.batch_id == "b1")
    assert change.kind == "moved" and change.after.startswith("Near")
    assert "must be on sale by" in change.reason
    assert delayed.effect.startswith(
        "Delay to mid +6h → 1 tomato batch no longer reaches Mid fresh → moved to Near"
    )


def test_truck_loss_is_respected_and_still_valid():
    s = generate(1011)
    plan = plan_lading(s, "lading-point")
    lost = s.trucks[0].id
    result = replan(s, plan, Disruption(kind="truck_loss", label="Truck lost", at_slot=2, truck_id=lost))
    late_trips = [t for t in result.plan.trips if t.truck_id == lost and int(t.slot_id[1:]) >= 2]
    assert late_trips == []
    assert validate(result.scenario, json.loads(result.plan.model_dump_json()))["status"] == "PASS"


def test_new_order_is_served_inside_its_deadline():
    s = two_markets()
    plan = plan_lading(s, "lading-point")
    order = NewOrder(
        id="hotel_order",
        name="Hotel order",
        commodity_id="tomato",
        kg=1000,
        price_inr_per_kg=40,
        deliver_by_h=10,
        travel_h=2,
        transport_inr_per_kg=0.8,
        handling_h=1,
        handling_inr_per_kg=0.5,
    )
    result = replan(
        s, plan, Disruption(kind="new_order", label="Hotel order 1 t tomato", at_slot=0, order=order)
    )
    served = [sh for sh in result.plan.shipments if sh.market_id == "hotel_order"]
    assert served and sum(sh.kg for sh in served) == pytest.approx(1000)
    assert validate(result.scenario, json.loads(result.plan.model_dump_json()))["status"] == "PASS"


def test_apply_freezes_departed_stock_and_drops_past_locks():
    s = two_markets()
    plan = plan_lading(s, "lading-point")
    after = apply(s, plan, Disruption(kind="truck_loss", label="t2 lost", at_slot=1, truck_id="t2"))
    assert after.policy.current_slot == 1
    assert {(d.batch_id, d.slot_id) for d in after.controls.dispatched} == {
        (sh.batch_id, sh.slot_id) for sh in plan.shipments if sh.slot_id == "s0"
    }
    assert next(t for t in after.trucks if t.id == "t2").unavailable_from_slot == 1


def test_replan_objective_equals_forecast_net_with_stock_on_the_road():
    s = generate(1003)
    plan = plan_lading(s, "lading-point")
    first = next(sh for sh in plan.shipments if sh.slot_id == "s0")
    result = replan(
        s,
        plan,
        Disruption(kind="route_delay", label="delay", at_slot=1, market_id=first.market_id, extra_h=4),
    )
    assert result.scenario["controls"]["dispatched"]
    assert result.plan.solver is not None
    assert result.plan.solver.objective_inr == pytest.approx(result.plan.expected.net_inr, abs=0.05)
