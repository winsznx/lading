"""The cost model. The only place money is computed.

Every arm (FIFO, FEFO, Lading-point, Lading-robust, ablations) and the simulator import these
functions. The validator in `validate/` deliberately re-implements them from the raw scenario so a
bug here can't grade itself.

Net INR = sales revenue - transport - handling - purchase value of spoiled kg.
Discount given up is reported as its own line and is already netted out of revenue.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

COST_MODEL_ID = "lading-cost-v1"


def sale_inr_per_kg(price_inr_per_kg: float, discount: float) -> float:
    return price_inr_per_kg * (1.0 - discount)


def discount_inr_per_kg(price_inr_per_kg: float, discount: float) -> float:
    return price_inr_per_kg * discount


def route_inr_per_kg(transport_inr_per_kg: float, handling_inr_per_kg: float) -> float:
    """Freight plus market handling, paid on every kg that is shipped, whether it sells or not."""
    return transport_inr_per_kg + handling_inr_per_kg


def spoilage_inr_per_kg(purchase_inr_per_kg: float) -> float:
    return purchase_inr_per_kg


def demand_cap_kg(base_demand_kg: float, elasticity: float, discount: float) -> float:
    return base_demand_kg * (1.0 + elasticity * discount)


@dataclass(frozen=True)
class Sale:
    kg: float
    price_inr_per_kg: float
    discount: float


@dataclass(frozen=True)
class Haul:
    kg: float
    transport_inr_per_kg: float
    handling_inr_per_kg: float


@dataclass(frozen=True)
class Loss:
    kg: float
    purchase_inr_per_kg: float


@dataclass(frozen=True)
class CostBreakdown:
    revenue_inr: float
    discount_given_up_inr: float
    transport_inr: float
    handling_inr: float
    spoilage_inr: float
    net_inr: float

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in asdict(self).items()}


def breakdown(sales: Iterable[Sale], hauls: Iterable[Haul], losses: Iterable[Loss]) -> CostBreakdown:
    revenue = discount = transport = handling = spoilage = 0.0
    for s in sales:
        revenue += s.kg * sale_inr_per_kg(s.price_inr_per_kg, s.discount)
        discount += s.kg * discount_inr_per_kg(s.price_inr_per_kg, s.discount)
    for h in hauls:
        transport += h.kg * h.transport_inr_per_kg
        handling += h.kg * h.handling_inr_per_kg
    for loss in losses:
        spoilage += loss.kg * spoilage_inr_per_kg(loss.purchase_inr_per_kg)
    return CostBreakdown(
        revenue_inr=revenue,
        discount_given_up_inr=discount,
        transport_inr=transport,
        handling_inr=handling,
        spoilage_inr=spoilage,
        net_inr=revenue - transport - handling - spoilage,
    )
