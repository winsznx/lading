"""Independent plan validator.

Takes a scenario and a plan as plain JSON and recomputes every constraint and every forecast total
from scratch. It imports nothing from this repo, not the planner, the baselines, the simulator, the
cost model or the scenario models, so a bug in any of them can't grade itself. A test fails the build
if that ever changes (`validate/test_independence.py`).

Usage: python -m validate.validator scenario.json plan.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

KG_TOL = 1e-3
INR_TOL = 1.0


class Report:
    def __init__(self) -> None:
        self.violations: list[dict[str, str]] = []
        self.checked: dict[str, int] = defaultdict(int)

    def check(self, name: str, ok: bool, message: str, ref: str) -> None:
        self.checked[name] += 1
        if not ok:
            self.violations.append({"check": name, "message": message, "ref": ref})

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if not self.violations else "FAIL",
            "violation_count": len(self.violations),
            "violations": self.violations,
            "checks": dict(sorted(self.checked.items())),
        }


def validate(scenario: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    r = Report()
    batches = {b["id"]: b for b in scenario["batches"]}
    markets = {m["id"]: m for m in scenario["markets"]}
    slots = {s["id"]: s for s in scenario["slots"]}
    trucks = {t["id"]: t for t in scenario["trucks"]}
    commodities = {c["id"]: c for c in scenario["commodities"]}
    offers = {(m["id"], o["commodity_id"]): o for m in scenario["markets"] for o in m["offers"]}
    policy = scenario["policy"]
    margin = policy["safety_margin_h"]
    levels = policy["discount_levels"]
    current = policy.get("current_slot", 0)
    dispatched: dict[tuple[str, str, str], float] = defaultdict(float)
    for d in scenario.get("controls", {}).get("dispatched", []):
        dispatched[(d["batch_id"], d["market_id"], d["slot_id"])] += d["kg"]

    r.check("plan.scenario", plan["scenario_id"] == scenario["id"], "plan is for another scenario", "scenario_id")

    prices: dict[tuple[str, str], float] = {}
    for i, p in enumerate(plan["prices"]):
        cell = (p["market_id"], p["commodity_id"])
        r.check("price.offer", cell in offers, f"{cell[0]} doesn't buy {cell[1]}", f"prices[{i}]")
        r.check("price.level", p["discount"] in levels, f"discount {p['discount']} not on the ladder", f"prices[{i}]")
        r.check("price.unique", cell not in prices, f"two prices for {cell}", f"prices[{i}]")
        prices[cell] = p["discount"]

    shipped_kg: dict[str, float] = defaultdict(float)
    destinations: dict[str, set[str]] = defaultdict(set)
    shipment_at: dict[tuple[str, str, str], float] = defaultdict(float)
    for i, sh in enumerate(plan["shipments"]):
        ref = f"shipments[{i}] {sh['batch_id']}"
        b, m, s = batches.get(sh["batch_id"]), markets.get(sh["market_id"]), slots.get(sh["slot_id"])
        r.check("ref.exists", b is not None and m is not None and s is not None, "unknown batch, market or slot", ref)
        if b is None or m is None or s is None:
            continue
        shipped_kg[b["id"]] += sh["kg"]
        destinations[b["id"]].add(m["id"])
        shipment_at[(b["id"], m["id"], s["id"])] += sh["kg"]
        key = (b["id"], m["id"], s["id"])
        if s["index"] < current:
            r.check("dispatched.match", abs(dispatched.get(key, 0.0) - sh["kg"]) <= KG_TOL,
                    f"slot {s['id']} has already left and this isn't what was dispatched on it", ref)
        cell = (m["id"], b["commodity_id"])
        r.check("market.buys", cell in offers, f"{m['id']} doesn't buy {b['commodity_id']}", ref)
        r.check("price.consistent", prices.get(cell, 0.0) == sh["discount"],
                f"shipment discount {sh['discount']} differs from the market price {prices.get(cell, 0.0)}", ref)
        if s["index"] < current:
            continue
        sale_h = s["depart_h"] + m["travel_h"] + m["handling_h"]
        latest = b["shelf_life_h"] - margin
        r.check("shelf_life", sale_h <= latest + 1e-9,
                f"on sale at {sale_h:.1f} h, must be by {latest:.1f} h ({b['shelf_life_h']:.1f} h shelf life - {margin:g} h margin)",
                ref)
        if m.get("deliver_by_h") is not None:
            r.check("deliver_by", sale_h <= m["deliver_by_h"] + 1e-9,
                    f"on sale at {sale_h:.1f} h, order deadline {m['deliver_by_h']:.1f} h", ref)

    for key, kg in dispatched.items():
        r.check("dispatched.match", abs(shipment_at.get(key, 0.0) - kg) <= KG_TOL,
                f"{kg:.0f} kg already left for {key[1]} at {key[2]} but the plan doesn't carry it", key[0])
    for bid, kg in shipped_kg.items():
        r.check("stock", kg <= batches[bid]["kg"] + KG_TOL, f"ships {kg:.0f} kg of {batches[bid]['kg']:.0f} kg", bid)
        r.check("one_market", len(destinations[bid]) == 1, f"split across markets {sorted(destinations[bid])}", bid)

    held = set(plan["held"])
    for bid in batches:
        r.check("held.consistent", (bid in held) == (bid not in shipped_kg), "held list disagrees with shipments", bid)

    seen_truck_slot: set[tuple[str, str]] = set()
    manifest_at: dict[tuple[str, str, str], float] = defaultdict(float)
    for i, trip in enumerate(plan["trips"]):
        ref = f"trips[{i}] {trip['truck_id']}@{trip['slot_id']}"
        t, s = trucks.get(trip["truck_id"]), slots.get(trip["slot_id"])
        r.check("ref.exists", t is not None and s is not None, "unknown truck or slot", ref)
        if t is None or s is None:
            continue
        load = sum(x["kg"] for x in trip["manifest"])
        r.check("trip.load", abs(load - trip["load_kg"]) <= KG_TOL, f"manifest {load:.0f} kg vs load {trip['load_kg']:.0f} kg", ref)
        r.check("truck.capacity", load <= t["capacity_kg"] + KG_TOL, f"{load:.0f} kg on a {t['capacity_kg']:.0f} kg truck", ref)
        unavailable = t.get("unavailable_from_slot")
        r.check("truck.available", unavailable is None or s["index"] < unavailable, "truck is out of service", ref)
        r.check("truck.once_per_slot", (t["id"], s["id"]) not in seen_truck_slot, "truck used twice in one slot", ref)
        seen_truck_slot.add((t["id"], s["id"]))
        for x in trip["manifest"]:
            r.check("ref.exists", x["market_id"] in markets and x["batch_id"] in batches, "unknown batch or market", ref)
            manifest_at[(x["batch_id"], x["market_id"], s["id"])] += x["kg"]

    for key in sorted(set(shipment_at) | set(manifest_at)):
        r.check("trip.manifest", abs(shipment_at.get(key, 0.0) - manifest_at.get(key, 0.0)) <= KG_TOL,
                f"{key[0]} to {key[1]} at {key[2]}: shipped {shipment_at.get(key, 0.0):.0f} kg, "
                f"loaded {manifest_at.get(key, 0.0):.0f} kg", key[0])

    totals = _forecast_totals(scenario, plan, batches, markets, slots, commodities, offers, prices)
    claimed = plan["expected"]
    for name, value in totals.items():
        tol = INR_TOL if name.endswith("_inr") else KG_TOL * 10
        r.check(f"total.{name}", abs(claimed[name] - value) <= tol,
                f"claimed {claimed[name]:.2f}, recomputed {value:.2f}", f"expected.{name}")

    report = r.as_dict()
    report["recomputed"] = {k: round(v, 2) for k, v in totals.items()}
    return report


def _forecast_totals(
    scenario: dict[str, Any],
    plan: dict[str, Any],
    batches: dict[str, Any],
    markets: dict[str, Any],
    slots: dict[str, Any],
    commodities: dict[str, Any],
    offers: dict[tuple[str, str], Any],
    prices: dict[tuple[str, str], float],
) -> dict[str, float]:
    """Book the plan against the forecast world, independently of cost_model.py and sim/."""
    revenue = given_up = transport = handling = spoilage = 0.0
    sold_total = unsold = expired = 0.0
    on_road: dict[str, float] = defaultdict(float)
    arriving: dict[tuple[str, str], float] = defaultdict(float)
    for trip in plan["trips"]:
        s = slots[trip["slot_id"]]
        for x in trip["manifest"]:
            m, b = markets[x["market_id"]], batches[x["batch_id"]]
            sale_h = s["depart_h"] + m["travel_h"] + m["handling_h"]
            kg = x["kg"]
            on_road[b["id"]] += kg
            transport += kg * m["transport_inr_per_kg"]
            handling += kg * m["handling_inr_per_kg"]
            purchase = commodities[b["commodity_id"]]["purchase_inr_per_kg"]
            late = m.get("deliver_by_h") is not None and sale_h > m["deliver_by_h"]
            if sale_h > b["shelf_life_h"]:
                expired += kg
                spoilage += kg * purchase
            elif late:
                unsold += kg
                spoilage += kg * purchase
            else:
                arriving[(m["id"], b["commodity_id"])] += kg
    for cell, kg in arriving.items():
        offer = offers.get(cell)
        d = prices.get(cell, 0.0)
        cap = offer["demand_kg"] * (1 + commodities[cell[1]]["elasticity"] * d) if offer else 0.0
        sold = min(kg, cap)
        price = offer["price_inr_per_kg"] if offer else 0.0
        revenue += sold * price * (1 - d)
        given_up += sold * price * d
        sold_total += sold
        unsold += kg - sold
        spoilage += (kg - sold) * commodities[cell[1]]["purchase_inr_per_kg"]
    hub = carry = 0.0
    for b in batches.values():
        left = b["kg"] - on_road.get(b["id"], 0.0)
        if left <= 1e-9:
            continue
        if b["shelf_life_h"] <= scenario["policy"]["horizon_h"]:
            hub += left
            spoilage += left * commodities[b["commodity_id"]]["purchase_inr_per_kg"]
        else:
            carry += left
    return {
        "revenue_inr": revenue,
        "discount_given_up_inr": given_up,
        "transport_inr": transport,
        "handling_inr": handling,
        "spoilage_inr": spoilage,
        "net_inr": revenue - transport - handling - spoilage,
        "sold_kg": sold_total,
        "unsold_kg": unsold,
        "expired_in_transit_kg": expired,
        "hub_spoiled_kg": hub,
        "carry_over_kg": carry,
    }


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m validate.validator scenario.json plan.json")
    with open(sys.argv[1]) as f:
        scenario = json.load(f)
    with open(sys.argv[2]) as f:
        plan = json.load(f)
    report = validate(scenario, plan)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
