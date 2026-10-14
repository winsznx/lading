import pytest

from cost_model import (
    Haul,
    Loss,
    Sale,
    breakdown,
    demand_cap_kg,
    discount_inr_per_kg,
    route_inr_per_kg,
    sale_inr_per_kg,
)


def test_unit_prices():
    assert sale_inr_per_kg(30.0, 0.2) == pytest.approx(24.0)
    assert discount_inr_per_kg(30.0, 0.2) == pytest.approx(6.0)
    assert route_inr_per_kg(1.3, 0.8) == pytest.approx(2.1)


def test_demand_uplift():
    assert demand_cap_kg(1000, 1.5, 0.3) == pytest.approx(1450)
    assert demand_cap_kg(1000, 1.5, 0.0) == pytest.approx(1000)


def test_breakdown_hand_computed():
    # 800 kg tomato sold at 30/kg with 20% off -> 19,200 revenue, 4,800 given up.
    # 1,000 kg hauled at 1.3 freight + 0.8 handling -> 1,300 + 800.
    # 200 kg unsold tomato bought at 14/kg -> 2,800 spoilage.
    b = breakdown([Sale(800, 30.0, 0.2)], [Haul(1000, 1.3, 0.8)], [Loss(200, 14.0)])
    assert b.revenue_inr == pytest.approx(19_200)
    assert b.discount_given_up_inr == pytest.approx(4_800)
    assert b.transport_inr == pytest.approx(1_300)
    assert b.handling_inr == pytest.approx(800)
    assert b.spoilage_inr == pytest.approx(2_800)
    assert b.net_inr == pytest.approx(19_200 - 1_300 - 800 - 2_800)


def test_breakdown_of_nothing_is_zero():
    b = breakdown([], [], [])
    assert b.net_inr == 0 and b.revenue_inr == 0


def test_hub_spoilage_only():
    # No-op plan: 1,500 kg leafy greens bought at 18/kg rot at the hub.
    b = breakdown([], [], [Loss(1500, 18.0)])
    assert b.net_inr == pytest.approx(-27_000)
