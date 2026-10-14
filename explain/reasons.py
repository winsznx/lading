"""Reason engine. Plain sentences generated only from decision objects. No language model.

Every number in a sentence is a field of the decision it explains, so a reason can't say anything the
planner didn't plan on.
"""

from __future__ import annotations

from planner.decisions import Alternative, Decision


def inr(x: float) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567."""
    sign = "-" if x < 0 else ""
    whole = f"{abs(round(x)):d}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}"


def kg(x: float) -> str:
    return f"{x:,.0f} kg"


def hours(x: float) -> str:
    return f"{x:.0f}h" if abs(x - round(x)) < 0.05 else f"{x:.1f}h"


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def short(name: str | None) -> str:
    """'Chennai (Koyambedu)' -> 'Chennai'. Dispatchers name mandis by city."""
    return (name or "").split(" (")[0]


def _basis_note(decision: Decision) -> str:
    return " at P90 travel and P10 shelf life" if decision.basis == "robust" else ""


def alternative_sentence(decision: Decision, alt: Alternative) -> str:
    name = short(alt.market_name)
    if alt.code == "EXPIRED_ON_ARRIVAL":
        assert alt.sale_h is not None and alt.limit_h is not None
        return (
            f"{name}: on sale at {hours(alt.sale_h)} at the earliest, but it must be on sale by {hours(alt.limit_h)} "
            f"({hours(decision.plan_shelf_h)} shelf life left{_basis_note(decision)})."
        )
    if alt.code == "DEADLINE":
        assert alt.sale_h is not None and alt.deadline_h is not None
        return f"{name}: the order closes at {hours(alt.deadline_h)} and the earliest it can be on sale is {hours(alt.sale_h)}."
    if alt.code == "VETOED":
        return f"{name}: vetoed by the dispatcher."
    if alt.code == "TRUCK_FULL":
        return f"{name}: trucks are full through {alt.last_slot_label}, the last slot that reaches it fresh."
    if alt.code == "DEMAND_MET":
        return f"{name}: its {decision.commodity_name.lower()} demand is already covered by other batches."
    if alt.code == "LOWER_NET":
        assert alt.delta_inr is not None and alt.net_inr is not None
        return f"{name}: {inr(alt.delta_inr)} less for this batch ({inr(alt.net_inr)} vs {inr(decision.net_inr)})."
    if alt.code == "PLAN_TRADEOFF":
        assert alt.delta_inr is not None
        return (
            f"{name}: {inr(-alt.delta_inr)} more for this batch alone, but the joint plan earns more with that "
            f"truck room and demand given to other stock."
        )
    assert alt.net_inr is not None
    outcome = "it would spoil there" if alt.net_inr < 0 else "it would carry over unsold"
    return f"Hold at hub: {inr(alt.net_inr)}, {outcome}."


def _tempting(decision: Decision) -> Alternative | None:
    """The rejected market a dispatcher would most likely ask about: the one where the plan's local
    reason is a hard constraint, otherwise the closest call on money."""
    markets = [a for a in decision.alternatives if a.market_id is not None]
    for code in ("EXPIRED_ON_ARRIVAL", "DEADLINE", "TRUCK_FULL", "DEMAND_MET", "VETOED"):
        hits = [a for a in markets if a.code == code]
        if hits:
            return hits[0]
    priced = [a for a in markets if a.delta_inr is not None]
    return min(priced, key=lambda a: abs(a.delta_inr or 0.0)) if priced else None


def headline(decision: Decision) -> str:
    if decision.status != "assigned":
        return hold_sentence(decision)
    chosen = short(decision.market_name)
    alt = _tempting(decision)
    other = short(alt.market_name) if alt else ""
    if alt is None:
        line = f"{chosen}: the only market buying {decision.commodity_name.lower()} it can reach fresh."
    elif alt.code == "EXPIRED_ON_ARRIVAL":
        assert alt.sale_h is not None and alt.limit_h is not None
        if alt.sale_h > decision.plan_shelf_h:
            line = f"{chosen}, not {other}: {other} arrival {hours(alt.sale_h)} vs {hours(decision.plan_shelf_h)} shelf life left."
        else:
            margin = decision.plan_shelf_h - alt.limit_h
            line = (
                f"{chosen}, not {other}: {other} arrival {hours(alt.sale_h)} is inside the {hours(margin)} safety margin "
                f"of its {hours(decision.plan_shelf_h)} shelf life."
            )
    elif alt.code == "DEADLINE":
        line = f"{chosen}, not {other}: {other}'s order closes before it can arrive."
    elif alt.code == "TRUCK_FULL":
        line = f"{chosen}, not {other}: trucks are full through {alt.last_slot_label}."
    elif alt.code == "DEMAND_MET":
        line = f"{chosen}, not {other}: {other} demand already covered."
    elif alt.code == "VETOED":
        line = f"{chosen}, not {other}: vetoed by the dispatcher."
    elif alt.code == "LOWER_NET":
        assert alt.delta_inr is not None
        line = f"{chosen}, not {other}: {inr(alt.delta_inr)} more net here."
    else:
        line = f"{chosen}, not {other}: the joint plan earns more with {other}'s room used by other stock."
    if decision.discount:
        line += f" {pct(decision.discount)} off at {chosen} lifts demand to sell it."
    if decision.locked:
        line = "Locked by the dispatcher. " + line
    return line


def hold_sentence(decision: Decision) -> str:
    code = decision.hold_code
    if code == "INFEASIBLE_DEMAND":
        return "Cannot be sold fresh: no market can have it on sale before it expires. Discount locally or salvage."
    if code == "TOO_RISKY":
        return (
            f"Held: at P10 shelf life ({hours(decision.plan_shelf_h)}) and P90 travel no market gets it on sale in time, "
            f"though the forecast ({hours(decision.shelf_h)}) says one might."
        )
    if code == "CARRY_OVER":
        return f"Kept for tomorrow: {hours(decision.shelf_h)} of shelf life left, and today's truck room earns more on shorter-life stock."
    if code == "NO_ROOM":
        return "Held: no truck room or demand left at any market it can reach fresh."
    best = max(
        (a for a in decision.alternatives if a.net_inr is not None and a.market_id is not None),
        key=lambda a: a.net_inr or 0.0,
        default=None,
    )
    if best is not None and best.net_inr is not None:
        return f"Held: shipping it loses more than it saves (best option {short(best.market_name)}, {inr(best.net_inr)} vs {inr(decision.net_inr)} at the hub)."
    return "Held: shipping it loses more than it saves."


def explain(decision: Decision) -> dict[str, object]:
    return {
        "batch_id": decision.batch_id,
        "headline": headline(decision),
        "alternatives": [alternative_sentence(decision, a) for a in decision.alternatives],
    }
