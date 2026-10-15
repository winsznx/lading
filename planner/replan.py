"""Disruption replans and the dispatcher's lock and veto.

A replan freezes everything that left before the disruption became known (it is stock on the road, kept
as `controls.dispatched`), applies the disruption to what the planner knows, and re-solves the slots
that are still open. The result carries a diff against the previous plan, a reason per changed batch,
and one cause-to-effect line.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from explain.reasons import alternative_sentence, headline, pct
from plan_model import Plan
from planner.decisions import Decision, build_decisions
from scenarios.loader import parse
from scenarios.model import Scenario

Kind = Literal["route_delay", "truck_loss", "demand_spike", "new_order"]


class NewOrder(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_\-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    commodity_id: str
    kg: float = Field(gt=0)
    price_inr_per_kg: float = Field(gt=0)
    deliver_by_h: float = Field(gt=0)
    travel_h: float = Field(gt=0)
    transport_inr_per_kg: float = Field(ge=0)
    handling_h: float = Field(ge=0)
    handling_inr_per_kg: float = Field(ge=0)


class Disruption(BaseModel):
    kind: Kind
    label: str = Field(min_length=1, max_length=160)
    at_slot: int = Field(ge=0, description="Index of the first slot that hasn't left when the news arrives.")
    market_id: str | None = None
    extra_h: float | None = Field(default=None, gt=0)
    truck_id: str | None = None
    commodity_id: str | None = None
    factor: float | None = Field(default=None, gt=0)
    order: NewOrder | None = None


class Change(BaseModel):
    batch_id: str
    kind: Literal["moved", "retimed", "rediscounted", "dropped", "added"]
    before: str
    after: str
    reason: str


class ReplanResult(BaseModel):
    scenario: dict[str, Any]
    plan: Plan
    decisions: list[Decision]
    changes: list[Change]
    effect: str
    latency_s: float


def apply(scenario: Scenario, previous: Plan, disruption: Disruption) -> Scenario:
    """The scenario as the planner knows it once the disruption is known at `at_slot`."""
    raw = json.loads(scenario.model_dump_json())
    index = {s.id: s.index for s in scenario.slots}
    if disruption.at_slot >= len(scenario.slots):
        raise ValueError("disruption arrives after the last slot")
    at = max(disruption.at_slot, scenario.policy.current_slot)
    raw["policy"]["current_slot"] = at
    gone = [sh for sh in previous.shipments if index[sh.slot_id] < at]
    raw["controls"]["dispatched"] = [
        {"batch_id": sh.batch_id, "market_id": sh.market_id, "slot_id": sh.slot_id, "kg": sh.kg}
        for sh in gone
    ]
    raw["controls"]["locks"] = [lk for lk in raw["controls"]["locks"] if index[lk["slot_id"]] >= at]

    if disruption.kind == "route_delay":
        market = _find(raw["markets"], disruption.market_id, "market")
        market["travel_h"] = round(market["travel_h"] + (disruption.extra_h or 0.0), 2)
    elif disruption.kind == "truck_loss":
        truck = _find(raw["trucks"], disruption.truck_id, "truck")
        truck["unavailable_from_slot"] = at
    elif disruption.kind == "demand_spike":
        market = _find(raw["markets"], disruption.market_id, "market")
        offer = next((o for o in market["offers"] if o["commodity_id"] == disruption.commodity_id), None)
        if offer is None:
            raise ValueError(f"{market['id']} doesn't buy {disruption.commodity_id}")
        offer["demand_kg"] = round(offer["demand_kg"] * (disruption.factor or 1.0), 1)
    elif disruption.kind == "new_order":
        order = disruption.order
        if order is None:
            raise ValueError("new_order needs an order")
        raw["markets"].append(
            {
                "id": order.id,
                "name": order.name,
                "travel_h": order.travel_h,
                "transport_inr_per_kg": order.transport_inr_per_kg,
                "handling_h": order.handling_h,
                "handling_inr_per_kg": order.handling_inr_per_kg,
                "deliver_by_h": order.deliver_by_h,
                "offers": [
                    {
                        "commodity_id": order.commodity_id,
                        "price_inr_per_kg": order.price_inr_per_kg,
                        "demand_kg": order.kg,
                    }
                ],
            }
        )
    return parse(raw)


def _find(items: list[dict[str, Any]], item_id: str | None, what: str) -> dict[str, Any]:
    found = next((x for x in items if x["id"] == item_id), None)
    if found is None:
        raise ValueError(f"unknown {what} '{item_id}'")
    return found


def _where(scenario: Scenario, plan: Plan) -> dict[str, tuple[str, tuple[str, ...], float]]:
    slots = {s.id: s for s in scenario.slots}
    out: dict[str, tuple[str, tuple[str, ...], float]] = {}
    for sh in plan.shipments:
        m, labels, d = out.get(sh.batch_id, (sh.market_id, (), sh.discount))
        out[sh.batch_id] = (m, (*labels, slots[sh.slot_id].label), d)
    return out


def _describe(scenario: Scenario, spot: tuple[str, tuple[str, ...], float] | None) -> str:
    if spot is None:
        return "held at hub"
    market, labels, discount = spot
    name = scenario.market(market).name.split(" (")[0]
    off = f", {pct(discount)} off" if discount else ""
    return f"{name} at {' + '.join(labels)}{off}"


def diff(
    old_scenario: Scenario, old: Plan, new_scenario: Scenario, new: Plan, decisions: list[Decision]
) -> list[Change]:
    before, after = _where(old_scenario, old), _where(new_scenario, new)
    by_batch = {d.batch_id: d for d in decisions}
    changes = []
    for b in new_scenario.batches:
        was, now = before.get(b.id), after.get(b.id)
        if was == now:
            continue
        decision = by_batch[b.id]
        if was and now and was[0] != now[0]:
            kind: Literal["moved", "retimed", "rediscounted", "dropped", "added"] = "moved"
            old_alt = next((a for a in decision.alternatives if a.market_id == was[0]), None)
            reason = alternative_sentence(decision, old_alt) if old_alt else headline(decision)
        elif was and now and was[1] != now[1]:
            kind, reason = "retimed", headline(decision)
        elif was and now:
            kind, reason = "rediscounted", headline(decision)
        elif was:
            kind, reason = "dropped", headline(decision)
        else:
            kind, reason = "added", headline(decision)
        changes.append(
            Change(
                batch_id=b.id,
                kind=kind,
                before=_describe(old_scenario, was),
                after=_describe(new_scenario, now),
                reason=reason,
            )
        )
    return changes


def effect_line(
    disruption: Disruption, new_scenario: Scenario, changes: list[Change], decisions: list[Decision]
) -> str:
    """One line from cause to effect, built only from the diff and the new decision objects."""
    by_batch = {d.batch_id: d for d in decisions}
    parts = [disruption.label]
    moved = [c for c in changes if c.kind == "moved"]
    expired = [c for c in moved if "must be on sale by" in c.reason or "order closes" in c.reason]
    if expired:
        commodities = Counter(by_batch[c.batch_id].commodity_name.lower() for c in expired)
        what = ", ".join(f"{n} {name}" for name, n in commodities.most_common())
        target = Counter(c.before.split(" at ")[0] for c in expired).most_common(1)[0][0]
        verb = "no longer reach" if len(expired) > 1 else "no longer reaches"
        parts.append(f"{what} batch{'es' if len(expired) > 1 else ''} {verb} {target} fresh")
    if moved:
        targets = Counter(c.after.split(" at ")[0] for c in (expired or moved)).most_common(2)
        parts.append("moved to " + " and ".join(name for name, _ in targets))
    rediscounted = [
        c for c in changes if c.kind == "rediscounted" or (c.kind == "moved" and "off" in c.after)
    ]
    if rediscounted:
        parts.append(f"{len(rediscounted)} re-priced")
    added = [c for c in changes if c.kind == "added"]
    if added:
        dest = Counter(c.after.split(" at ")[0] for c in added).most_common(1)[0][0]
        parts.append(
            f"{len(added)} held batch{'es' if len(added) > 1 else ''} now ship, mostly to {dest}"
            if len(added) > 1
            else f"1 held batch now ships to {dest}"
        )
    dropped = [c for c in changes if c.kind == "dropped"]
    if dropped:
        parts.append(f"{len(dropped)} now held")
    retimed = [c for c in changes if c.kind == "retimed"]
    if retimed:
        parts.append(f"{len(retimed)} retimed")
    if len(parts) == 1:
        parts.append("no batch needs to change")
    return " → ".join(parts)


def replan(
    scenario: Scenario, previous: Plan, disruption: Disruption, arm: str = "lading-point"
) -> ReplanResult:
    from planner.milp import plan_lading

    started = time.perf_counter()
    new_scenario = apply(scenario, previous, disruption)
    plan = plan_lading(new_scenario, arm, previous=previous)
    decisions = build_decisions(new_scenario, plan)
    changes = diff(scenario, previous, new_scenario, plan, decisions)
    return ReplanResult(
        scenario=json.loads(new_scenario.model_dump_json()),
        plan=plan,
        decisions=decisions,
        changes=changes,
        effect=effect_line(disruption, new_scenario, changes, decisions),
        latency_s=round(time.perf_counter() - started, 3),
    )
