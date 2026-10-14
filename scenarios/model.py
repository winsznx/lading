"""Scenario data model.

The Pydantic models here are the single definition of a scenario. `schemas/scenario.json` is generated
from them (`python -m scenarios.model`) and a test fails if the committed schema drifts.

Two blocks deserve care:

* ``uncertainty`` is disclosed to every arm. Lading-robust derives its conservative inputs from it.
* ``execution`` holds shocks that only the simulator reads (a route delay or a truck breakdown nobody
  saw coming). No planner or baseline may read it; `planner/test_information_parity.py` enforces that.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "lading-scenario-v1"

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_\-]*$")]
NonNegFloat = Annotated[float, Field(ge=0)]
PosFloat = Annotated[float, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Hub(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=120)


class Commodity(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=80)
    purchase_inr_per_kg: PosFloat = Field(description="What the hub paid per kg. Spoiled kg cost this much.")
    elasticity: NonNegFloat = Field(description="Demand uplift = base demand x (1 + elasticity x discount).")
    shelf_life_sigma: Annotated[float, Field(ge=0, le=0.5)] = Field(
        description="Relative std-dev of realized shelf life around the batch estimate."
    )


class Batch(Strict):
    id: Id
    commodity_id: Id
    kg: PosFloat
    shelf_life_h: PosFloat = Field(description="Estimated hours until the batch is no longer saleable, from t=0.")
    arrived_h_ago: NonNegFloat = Field(description="Hours since the batch reached the hub. FIFO sorts on this.")
    origin: str = Field(min_length=1, max_length=120)


class Offer(Strict):
    commodity_id: Id
    price_inr_per_kg: PosFloat
    demand_kg: NonNegFloat = Field(description="Forecast demand at list price over the planning window.")


class Market(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=120)
    travel_h: PosFloat = Field(description="Forecast hub-to-market travel time.")
    transport_inr_per_kg: NonNegFloat
    handling_h: NonNegFloat = Field(description="Unloading and auction time before stock is on sale.")
    handling_inr_per_kg: NonNegFloat
    deliver_by_h: PosFloat | None = Field(
        default=None, description="Optional hard deadline (sale-ready time) for order-type destinations."
    )
    offers: list[Offer] = Field(min_length=1)


class Truck(Strict):
    id: Id
    capacity_kg: PosFloat
    unavailable_from_slot: Annotated[int, Field(ge=0)] | None = Field(
        default=None, description="Known at plan time: the truck can't take trips from this slot index on."
    )


class Slot(Strict):
    id: Id
    index: Annotated[int, Field(ge=0)]
    depart_h: NonNegFloat
    label: str = Field(min_length=1, max_length=32, description="Clock label shown to the dispatcher.")


class Policy(Strict):
    horizon_h: PosFloat = Field(description="Undispatched stock that expires before this is spoiled at the hub.")
    safety_margin_h: NonNegFloat = Field(description="Sale-ready time must be at least this far before expiry.")
    turnaround_buffer_h: NonNegFloat = Field(description="Load and unload time added to a truck's round trip.")
    discount_levels: list[Annotated[float, Field(ge=0, lt=1)]] = Field(min_length=1, max_length=8)
    current_slot: Annotated[int, Field(ge=0)] = Field(
        default=0, description="First slot that can still dispatch. Earlier slots have left (replans)."
    )


class TravelDelay(Strict):
    median_frac: NonNegFloat = Field(description="Median realized delay as a fraction of forecast travel time.")
    sigma_log: NonNegFloat = Field(description="Log-space std-dev of the delay fraction (right-skewed).")


class Uncertainty(Strict):
    demand_sigma: Annotated[float, Field(ge=0, le=1)] = Field(description="Relative std-dev of realized demand.")
    travel_delay: TravelDelay


class RouteShock(Strict):
    market_id: Id
    extra_h: PosFloat


class DemandShock(Strict):
    market_id: Id
    factor: NonNegFloat


class TruckLoss(Strict):
    truck_id: Id
    from_slot: Annotated[int, Field(ge=0)]


class Execution(Strict):
    """Shocks that happen in the realized world. Only `sim/` reads this block."""

    route_delay: RouteShock | None = None
    demand_shock: DemandShock | None = None
    truck_loss: TruckLoss | None = None
    elasticity_factor: PosFloat = Field(
        default=1.0, description="Realized elasticity = disclosed elasticity x this factor (sensitivity sweep)."
    )


class Lock(Strict):
    batch_id: Id
    market_id: Id
    slot_id: Id


class Veto(Strict):
    batch_id: Id
    market_id: Id


class Controls(Strict):
    """Dispatcher overrides. Locks force an assignment, vetoes forbid a batch-market pair."""

    locks: list[Lock] = Field(default_factory=list)
    vetoes: list[Veto] = Field(default_factory=list)


class CostModelRef(Strict):
    id: Literal["lading-cost-v1"]


class Scenario(Strict):
    schema_version: Literal["lading-scenario-v1"]
    id: Id
    label: str = Field(min_length=1, max_length=200)
    source: Literal["generator", "organizer", "curated"]
    synthetic: bool
    seed: int | None = None
    family: str = Field(min_length=1, max_length=40)
    hub: Hub
    cost_model: CostModelRef
    commodities: list[Commodity] = Field(min_length=1)
    batches: list[Batch] = Field(min_length=1)
    markets: list[Market] = Field(min_length=1)
    trucks: list[Truck] = Field(min_length=1)
    slots: list[Slot] = Field(min_length=1)
    policy: Policy
    uncertainty: Uncertainty
    execution: Execution = Field(default_factory=Execution)
    controls: Controls = Field(default_factory=Controls)

    def commodity(self, commodity_id: str) -> Commodity:
        return next(c for c in self.commodities if c.id == commodity_id)

    def market(self, market_id: str) -> Market:
        return next(m for m in self.markets if m.id == market_id)

    def batch(self, batch_id: str) -> Batch:
        return next(b for b in self.batches if b.id == batch_id)

    def slot(self, slot_id: str) -> Slot:
        return next(s for s in self.slots if s.id == slot_id)

    def offer(self, market_id: str, commodity_id: str) -> Offer | None:
        return next((o for o in self.market(market_id).offers if o.commodity_id == commodity_id), None)


def json_schema() -> dict[str, object]:
    schema = Scenario.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://lading.dev/schemas/scenario.json"
    return schema


if __name__ == "__main__":
    print(json.dumps(json_schema(), indent=2, sort_keys=True))
