"""Plan format shared by every arm, the simulator and the API.

The validator in `validate/` reads plans as plain JSON and doesn't import this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Arm = Literal[
    "fifo", "fefo", "lading-point", "lading-robust", "ablation-no-discount", "ablation-soft-shelf", "no-op"
]
Basis = Literal["point", "robust", "none"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Shipment(Strict):
    batch_id: str
    market_id: str
    slot_id: str
    kg: float
    discount: float
    locked: bool = False


class TripLoad(Strict):
    batch_id: str
    market_id: str
    kg: float


class Trip(Strict):
    """One truck leaving at one slot. Trucks are hired per slot, so a load can be split across them."""

    truck_id: str
    slot_id: str
    load_kg: float
    manifest: list[TripLoad]


class Price(Strict):
    market_id: str
    commodity_id: str
    discount: float


class Expected(Strict):
    """Totals under the forecast. Every arm reports these and the validator recomputes them."""

    revenue_inr: float
    discount_given_up_inr: float
    transport_inr: float
    handling_inr: float
    spoilage_inr: float
    net_inr: float
    sold_kg: float
    unsold_kg: float
    expired_in_transit_kg: float
    hub_spoiled_kg: float
    carry_over_kg: float


class SolverInfo(Strict):
    status: Literal["OPTIMAL", "TIME_LIMIT"]
    objective_inr: float
    bound_inr: float
    gap: float
    solve_s: float
    n_vars: int
    n_rows: int
    highs_version: str


class Plan(Strict):
    scenario_id: str
    arm: Arm
    basis: Basis
    shipments: list[Shipment]
    trips: list[Trip]
    prices: list[Price]
    held: list[str]
    infeasible: list[str] = Field(
        description="Batches no market can receive fresh at any slot (INFEASIBLE_DEMAND)."
    )
    expected: Expected
    solver: SolverInfo | None = None
