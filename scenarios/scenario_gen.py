"""Seeded, deterministic scenario generator.

Every number it draws comes from `scenarios/assumptions.json`, mirrored with units in docs/ASSUMPTIONS.md.
Names of hubs and mandis are real places for legibility. Every value attached to them is synthetic.

Usage: python -m scenarios.scenario_gen --seed 1007 [--family base] [--out path.json]
"""

from __future__ import annotations

import argparse
import json
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from scenarios.model import SCHEMA_VERSION, Scenario

ASSUMPTIONS_PATH = Path(__file__).resolve().parent / "assumptions.json"
PLAN_STREAM = 101
FAMILIES = ("base", "demand_shock", "route_delay", "truck_loss", "wide_shelf", "healthy", "infeasible")


@cache
def assumptions() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ASSUMPTIONS_PATH.read_text())
    return data


def _r(x: float, nd: int = 2) -> float:
    return float(round(float(x), nd))


def _slot_label(depart_h: float, start_clock_h: int = 6) -> str:
    total = start_clock_h + depart_h
    day = int(total // 24) + 1
    return f"D{day} {int(total % 24):02d}:00"


def generate(seed: int, family: str = "base") -> Scenario:
    if family not in FAMILIES:
        raise ValueError(f"unknown family '{family}', expected one of {FAMILIES}")
    a = assumptions()
    rng = np.random.default_rng(np.random.SeedSequence([seed, PLAN_STREAM]))

    hub = a["hubs"][int(rng.integers(len(a["hubs"])))]
    n_markets = int(rng.integers(a["market_count"][0], a["market_count"][1] + 1))
    picked = sorted(
        rng.choice(len(hub["markets"]), size=n_markets, replace=False).tolist(),
        key=lambda i: (hub["markets"][i]["travel_h"], hub["markets"][i]["id"]),
    )
    market_specs = [hub["markets"][i] for i in picked]

    commodity_ids = list(a["commodities"])
    shares = np.array([a["commodities"][c]["share"] for c in commodity_ids], dtype=float)
    shares /= shares.sum()

    n_batches = int(rng.integers(a["batch_count"][0], a["batch_count"][1] + 1))
    step = a["batch_kg_step"]
    batches: list[dict[str, Any]] = []
    for i in range(n_batches):
        cid = commodity_ids[int(rng.choice(len(commodity_ids), p=shares))]
        spec = a["commodities"][cid]
        kg = step * int(rng.integers(a["batch_kg"][0] // step, a["batch_kg"][1] // step + 1))
        shelf = rng.uniform(*spec["shelf_life_h"])
        if family == "healthy":
            shelf = shelf * 3 + 100
        batches.append(
            {
                "id": f"b{i + 1:02d}",
                "commodity_id": cid,
                "kg": float(kg),
                "shelf_life_h": _r(shelf, 1),
                "arrived_h_ago": _r(rng.uniform(*a["arrived_h_ago"]), 1),
                "origin": hub["origins"][int(rng.integers(len(hub["origins"])))],
            }
        )
    if family == "infeasible":
        for j in range(3):
            batches.append(
                {
                    "id": f"b{n_batches + j + 1:02d}",
                    "commodity_id": "leafy_greens",
                    "kg": 400.0 + 100 * j,
                    "shelf_life_h": 3.0,
                    "arrived_h_ago": 30.0,
                    "origin": hub["origins"][j % len(hub["origins"])],
                }
            )

    present = sorted({b["commodity_id"] for b in batches}, key=commodity_ids.index)
    stock_kg = {c: sum(b["kg"] for b in batches if b["commodity_id"] == c) for c in present}

    offers_by_market: list[list[str]] = []
    for _ in market_specs:
        offered = [c for c in present if rng.uniform() >= a["offer_drop_probability"]]
        offers_by_market.append(offered or [present[int(rng.integers(len(present)))]])
    for c in present:
        if not any(c in o for o in offers_by_market):
            offers_by_market[int(rng.integers(len(market_specs)))].append(c)

    ratio_lo, ratio_hi = a["demand_to_stock_ratio"]
    if family == "healthy":
        ratio_lo, ratio_hi = 1.6, 1.8
    demand_ratio = {c: rng.uniform(ratio_lo, ratio_hi) for c in present}
    weights = {
        (mi, c): spec["demand_weight"] * rng.uniform(0.7, 1.3)
        for mi, spec in enumerate(market_specs)
        for c in offers_by_market[mi]
    }
    weight_sum = {c: sum(w for (_, cc), w in weights.items() if cc == c) for c in present}

    markets: list[dict[str, Any]] = []
    for mi, spec in enumerate(market_specs):
        offers = []
        for c in sorted(offers_by_market[mi], key=commodity_ids.index):
            cspec = a["commodities"][c]
            price = cspec["base_price_inr_per_kg"] * spec["price_factor"]
            price *= 1 + a["price_jitter"] * rng.uniform(-1, 1)
            demand = stock_kg[c] * demand_ratio[c] * weights[(mi, c)] / weight_sum[c]
            offers.append({"commodity_id": c, "price_inr_per_kg": _r(price), "demand_kg": float(round(demand, -1))})
        handling_h = 0.5 * round(rng.uniform(*a["handling_h"]) / 0.5)
        markets.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "travel_h": float(spec["travel_h"]),
                "transport_inr_per_kg": _r(a["transport_inr_per_kg_base"] + a["transport_inr_per_kg_per_h"] * spec["travel_h"]),
                "handling_h": float(handling_h),
                "handling_inr_per_kg": _r(rng.uniform(*a["handling_inr_per_kg"])),
                "offers": offers,
            }
        )

    n_trucks = int(rng.integers(a["truck_count"][0], a["truck_count"][1] + 1))
    capacities = [float(a["truck_capacities_kg"][int(rng.integers(len(a["truck_capacities_kg"])))]) for _ in range(n_trucks)]
    if family == "healthy":
        capacities = [float(max(a["truck_capacities_kg"]))] * 4
    trucks = [{"id": f"t{i + 1}", "capacity_kg": cap} for i, cap in enumerate(capacities)]

    slots = [
        {"id": f"s{i}", "index": i, "depart_h": float(i * a["slot_interval_h"]), "label": _slot_label(i * a["slot_interval_h"])}
        for i in range(a["n_slots"])
    ]

    shelf_sigma_factor = a["shocks"]["wide_shelf_sigma_factor"] if family == "wide_shelf" else 1.0
    commodities = [
        {
            "id": c,
            "name": a["commodities"][c]["name"],
            "purchase_inr_per_kg": float(a["commodities"][c]["purchase_inr_per_kg"]),
            "elasticity": float(a["commodities"][c]["elasticity"]),
            "shelf_life_sigma": _r(min(0.5, a["commodities"][c]["shelf_life_sigma"] * shelf_sigma_factor), 3),
        }
        for c in present
    ]

    execution: dict[str, Any] = {}
    if family == "demand_shock":
        top = max(markets, key=lambda m: (max(o["price_inr_per_kg"] for o in m["offers"]), m["id"]))
        execution["demand_shock"] = {"market_id": top["id"], "factor": a["shocks"]["demand_shock_factor"]}
    elif family == "route_delay":
        victim = markets[int(rng.integers(len(markets)))]
        execution["route_delay"] = {"market_id": victim["id"], "extra_h": float(a["shocks"]["route_delay_extra_h"])}
    elif family == "truck_loss":
        biggest = max(trucks, key=lambda t: (t["capacity_kg"], t["id"]))
        execution["truck_loss"] = {"truck_id": biggest["id"], "from_slot": a["shocks"]["truck_loss_from_slot"]}

    raw = {
        "schema_version": SCHEMA_VERSION,
        "id": f"gen-{family}-{seed}",
        "label": f"Synthetic day, seed {seed} ({family})",
        "source": "generator",
        "synthetic": True,
        "seed": seed,
        "family": family,
        "hub": {"id": hub["id"], "name": hub["name"]},
        "cost_model": {"id": "lading-cost-v1"},
        "commodities": commodities,
        "batches": batches,
        "markets": markets,
        "trucks": trucks,
        "slots": slots,
        "policy": {
            "horizon_h": float(a["horizon_h"]),
            "safety_margin_h": float(a["safety_margin_h"]),
            "discount_levels": [float(x) for x in a["discount_levels"]],
        },
        "uncertainty": {
            "demand_sigma": float(a["demand_sigma"]),
            "travel_delay": {
                "median_frac": float(a["travel_delay_median_frac"]),
                "sigma_log": float(a["travel_delay_sigma_log"]),
            },
        },
        "execution": execution,
    }
    return Scenario.model_validate(raw)


def dump(scenario: Scenario) -> str:
    return json.dumps(scenario.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", default="base", choices=FAMILIES)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    text = dump(generate(args.seed, args.family))
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
