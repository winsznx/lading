"""Hand-built small scenarios for tests, the brute-force reference and the curated P4 case."""

from __future__ import annotations

from typing import Any

from scenarios.model import SCHEMA_VERSION, Scenario

COMMODITIES = {
    "tomato": {"name": "Tomato", "purchase_inr_per_kg": 14.0, "elasticity": 1.5, "shelf_life_sigma": 0.12},
    "leafy_greens": {"name": "Leafy greens", "purchase_inr_per_kg": 18.0, "elasticity": 1.2, "shelf_life_sigma": 0.15},
    "onion": {"name": "Onion", "purchase_inr_per_kg": 16.0, "elasticity": 0.6, "shelf_life_sigma": 0.05},
}


def market(
    mid: str,
    travel_h: float,
    offers: dict[str, tuple[float, float]],
    transport: float = 1.0,
    handling_h: float = 1.0,
    handling: float = 0.5,
    deliver_by_h: float | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": mid,
        "name": mid.replace("_", " ").title(),
        "travel_h": travel_h,
        "transport_inr_per_kg": transport,
        "handling_h": handling_h,
        "handling_inr_per_kg": handling,
        "offers": [{"commodity_id": c, "price_inr_per_kg": p, "demand_kg": d} for c, (p, d) in offers.items()],
    }
    if deliver_by_h is not None:
        out["deliver_by_h"] = deliver_by_h
    return out


def batch(bid: str, commodity: str, kg: float, shelf_h: float, arrived_h_ago: float = 0.0) -> dict[str, Any]:
    return {
        "id": bid,
        "commodity_id": commodity,
        "kg": kg,
        "shelf_life_h": shelf_h,
        "arrived_h_ago": arrived_h_ago,
        "origin": "Test farm",
    }


def scenario(
    batches: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    trucks: list[float],
    n_slots: int = 2,
    slot_h: float = 6.0,
    discounts: list[float] | None = None,
    margin_h: float = 2.0,
    sid: str = "tiny",
    **extra: Any,
) -> Scenario:
    used = sorted({b["commodity_id"] for b in batches} | {o["commodity_id"] for m in markets for o in m["offers"]})
    raw: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": sid,
        "label": f"Hand-built scenario {sid}",
        "source": "curated",
        "synthetic": True,
        "family": "tiny",
        "hub": {"id": "hub", "name": "Test hub"},
        "cost_model": {"id": "lading-cost-v1"},
        "commodities": [{"id": c, **COMMODITIES[c]} for c in used],
        "batches": batches,
        "markets": markets,
        "trucks": [{"id": f"t{i + 1}", "capacity_kg": cap} for i, cap in enumerate(trucks)],
        "slots": [
            {"id": f"s{i}", "index": i, "depart_h": i * slot_h, "label": f"T+{int(i * slot_h)}h"} for i in range(n_slots)
        ],
        "policy": {
            "horizon_h": 48.0,
            "safety_margin_h": margin_h,
            "discount_levels": discounts if discounts is not None else [0.0, 0.2],
        },
        "uncertainty": {"demand_sigma": 0.2, "travel_delay": {"median_frac": 0.08, "sigma_log": 0.6}},
    }
    raw.update(extra)
    return Scenario.model_validate(raw)
