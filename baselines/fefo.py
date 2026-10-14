"""FEFO-greedy: the bar Lading has to beat (PRD section 5).

This is the rule a careful human dispatcher follows, and it gets every fact Lading gets:
the same forecast, the same cost model, the same safety margin, the same truck turnaround.

Decision rule:

1. Dispatcher locks are placed first and vetoed batch-market pairs are never used.
2. Batches are taken in order of shelf life left, shortest first (ties: bigger batch, then id).
3. For each batch, every market that buys it is a candidate if the stock can be on sale there, inside
   any order deadline, at least the safety margin before expiry, and the market still has forecast
   demand left. The slot is the earliest such slot with truck room (existing trip spare first, then
   a free truck whose round trip doesn't clash with its other trips).
4. Each candidate is scored by net margin on the batch: kg it can expect to sell x sale price, minus
   freight and handling on every kg, minus the purchase value of the kg that won't sell. The batch
   size is fixed, so this ranks markets exactly as per-kg margin does. The best-scoring market wins
   (ties: earlier slot, then market id).
5. If the batch would otherwise expire unsold (no market can take it before it expires inside the
   horizon, or the best market can't sell all of it), FEFO also prices a markdown to the deepest
   discount at each market, counting the price cut on stock already headed there, and takes it
   when it beats the best undiscounted option.
6. The batch only ships if the chosen option beats leaving it at the hub, where a batch that expires
   inside the horizon is a total loss and one that outlives it carries over.
"""

from __future__ import annotations

from collections import defaultdict

import cost_model
from baselines.fleet import Fleet
from plan_assembly import assemble
from plan_model import Plan
from scenarios.model import Batch, Market, Scenario, Slot
from world import World


def plan_fefo(scenario: Scenario) -> Plan:
    world = World(scenario, "point")
    fleet = Fleet(world)
    vetoed = {(v.batch_id, v.market_id) for v in scenario.controls.vetoes}
    deepest = max(scenario.policy.discount_levels)
    discount: dict[tuple[str, str], float] = defaultdict(float)
    shipped: dict[tuple[str, str], float] = defaultdict(float)
    assignments: dict[str, tuple[str, str]] = {}
    commodity = {c.id: c for c in scenario.commodities}

    def room_left(m: Market, cid: str, d: float) -> float:
        offer = scenario.offer(m.id, cid)
        assert offer is not None
        return cost_model.demand_cap_kg(offer.demand_kg, commodity[cid].elasticity, d) - shipped[(m.id, cid)]

    def earliest_slot(b: Batch, m: Market) -> tuple[Slot, list[str]] | None:
        for s in world.open_slots:
            if not world.fresh_on_sale(b, m, s):
                continue
            room = fleet.plan_room(m, s, b.kg)
            if room is not None:
                return s, room
        return None

    def value(b: Batch, m: Market, d: float) -> float:
        cid = b.commodity_id
        sold = min(b.kg, max(room_left(m, cid, d), 0.0))
        unit_sale = cost_model.sale_inr_per_kg(scenario.list_price(m.id, cid), d)
        unit_route = cost_model.route_inr_per_kg(m.transport_inr_per_kg, m.handling_inr_per_kg)
        unit_loss = cost_model.spoilage_inr_per_kg(commodity[cid].purchase_inr_per_kg)
        return sold * unit_sale - b.kg * unit_route - (b.kg - sold) * unit_loss

    def place(b: Batch, m: Market, s: Slot, room: list[str]) -> None:
        fleet.load(m, s, b.kg, room)
        assignments[b.id] = (m.id, s.id)
        shipped[(m.id, b.commodity_id)] += b.kg

    for lock in scenario.controls.locks:
        b, m, s = scenario.batch(lock.batch_id), scenario.market(lock.market_id), scenario.slot(lock.slot_id)
        room = fleet.plan_room(m, s, b.kg)
        if room is not None:
            place(b, m, s, room)

    for b in sorted(scenario.batches, key=lambda b: (world.shelf_h(b), -b.kg, b.id)):
        if b.id in assignments:
            continue
        purchase = commodity[b.commodity_id].purchase_inr_per_kg
        hold = -b.kg * cost_model.spoilage_inr_per_kg(purchase) if world.expires_in_horizon(b) else 0.0
        markets = [m for m in scenario.markets if world.sells(b, m) and (b.id, m.id) not in vetoed]

        best: tuple[float, int, str, Market, Slot, list[str]] | None = None
        for m in markets:
            d = discount[(m.id, b.commodity_id)]
            if room_left(m, b.commodity_id, d) <= 0:
                continue
            found = earliest_slot(b, m)
            if found is None:
                continue
            s, room = found
            key = (value(b, m, d), -s.index, m.id)
            if best is None or key > best[:3]:
                best = (*key, m, s, room)

        unsold_at_best = 0.0
        if best is not None:
            m = best[3]
            unsold_at_best = b.kg - min(b.kg, room_left(m, b.commodity_id, discount[(m.id, b.commodity_id)]))
        would_expire_unsold = unsold_at_best > 1e-9 or (best is None and world.expires_in_horizon(b))

        markdown: tuple[float, int, str, Market, Slot, list[str]] | None = None
        if would_expire_unsold:
            for m in markets:
                cell = (m.id, b.commodity_id)
                if discount[cell] >= deepest or room_left(m, b.commodity_id, deepest) <= 0:
                    continue
                found = earliest_slot(b, m)
                if found is None:
                    continue
                s, room = found
                selling_now = min(shipped[cell], room_left(m, b.commodity_id, discount[cell]) + shipped[cell])
                price_cut = selling_now * scenario.list_price(m.id, b.commodity_id) * (deepest - discount[cell])
                key = (value(b, m, deepest) - price_cut, -s.index, m.id)
                if markdown is None or key > markdown[:3]:
                    markdown = (*key, m, s, room)

        if markdown is not None and markdown[0] > hold and (best is None or markdown[0] > best[0]):
            discount[(markdown[3].id, b.commodity_id)] = deepest
            place(b, markdown[3], markdown[4], markdown[5])
        elif best is not None and best[0] > hold:
            place(b, best[3], best[4], best[5])

    return assemble(scenario, "fefo", "point", assignments, dict(fleet.trucks_by_cell), dict(discount))
