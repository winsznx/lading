"""The cause -> effect line under the plan board, built from decision objects."""

from __future__ import annotations

from collections import Counter

from explain.reasons import kg, pct, short
from plan_model import Plan
from planner.decisions import Decision
from scenarios.model import Scenario


def plan_effect(scenario: Scenario, plan: Plan, decisions: list[Decision]) -> str:
    slot_index = {s.id: s.index for s in scenario.slots}
    label = {s.id: s.label for s in scenario.slots}
    assigned = [d for d in decisions if d.status == "assigned"]
    parts = []
    if plan.shipments:
        last = max(plan.shipments, key=lambda sh: slot_index[sh.slot_id]).slot_id
        parts.append(f"{len(assigned)} of {len(decisions)} batches out by {label[last]}")
    else:
        parts.append("No batch is worth shipping")

    blocked: Counter[str] = Counter()
    for d in assigned:
        expired = [a for a in d.alternatives if a.code == "EXPIRED_ON_ARRIVAL" and a.market_name]
        if expired:
            blocked[short(expired[0].market_name)] += 1
    if blocked:
        where, n = blocked.most_common(1)[0]
        parts.append(
            f"{n} short-life batch{'es' if n > 1 else ''} kept off {where}, where {'they' if n > 1 else 'it'}'d arrive expired"
        )

    marked = [p for p in plan.prices if p.discount > 0]
    if marked:
        cut_kg: dict[tuple[str, str, float], float] = {}
        for sh in plan.shipments:
            if sh.discount > 0:
                key = (sh.market_id, scenario.batch(sh.batch_id).commodity_id, sh.discount)
                cut_kg[key] = cut_kg.get(key, 0.0) + sh.kg
        (mid, cid, level), total = max(cut_kg.items(), key=lambda kv: (kv[1], kv[0]))
        name = scenario.commodity(cid).name.lower()
        parts.append(f"{name} {pct(level)} off at {short(scenario.market(mid).name)} to sell {kg(total)}")
        if len(marked) > 1:
            parts.append(f"{len(marked) - 1} more price{'s' if len(marked) > 2 else ''} cut")

    carry = sum(1 for d in decisions if d.hold_code == "CARRY_OVER")
    if carry:
        parts.append(f"{carry} long-life batch{'es' if carry > 1 else ''} kept for tomorrow")
    stuck = sum(1 for d in decisions if d.hold_code == "INFEASIBLE_DEMAND")
    if stuck:
        parts.append(f"{stuck} can't be sold fresh anywhere")
    return " · ".join(parts)
