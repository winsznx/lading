"""Snapshot tests, one per reason type. Sentences are product copy, so any change must be deliberate."""

import pytest

from explain.reasons import alternative_sentence, headline, inr
from planner.decisions import Alternative, Decision


def decision(**over):
    base = dict(
        batch_id="b07",
        commodity_id="tomato",
        commodity_name="Tomato",
        kg=1200.0,
        origin="Niphad FPO",
        shelf_h=30.0,
        plan_shelf_h=26.0,
        basis="robust",
        status="assigned",
        market_id="pune",
        market_name="Pune",
        discount=0.0,
        legs=[],
        net_inr=24_600.0,
        hold_code=None,
        locked=False,
        alternatives=[],
    )
    base.update(over)
    return Decision(**base)


def alt(code, **over):
    return Alternative(market_id="mumbai", market_name="Mumbai", code=code, **over)


def test_inr_uses_indian_grouping():
    assert inr(1234567) == "₹12,34,567"
    assert inr(-950) == "-₹950"
    assert inr(100000) == "₹1,00,000"


@pytest.mark.parametrize(
    ("a", "expected"),
    [
        (alt("EXPIRED_ON_ARRIVAL", sale_h=31, limit_h=24),
         "Mumbai: on sale at 31h at the earliest, but it must be on sale by 24h (26h shelf life left at P90 travel and P10 shelf life)."),
        (alt("DEADLINE", sale_h=14, deadline_h=12), "Mumbai: the order closes at 12h and the earliest it can be on sale is 14h."),
        (alt("VETOED"), "Mumbai: vetoed by the dispatcher."),
        (alt("TRUCK_FULL", last_slot_label="D1 12:00"), "Mumbai: trucks are full through D1 12:00, the last slot that reaches it fresh."),
        (alt("DEMAND_MET"), "Mumbai: its tomato demand is already covered by other batches."),
        (alt("LOWER_NET", net_inr=21_000, delta_inr=3_600), "Mumbai: ₹3,600 less for this batch (₹21,000 vs ₹24,600)."),
        (alt("PLAN_TRADEOFF", net_inr=26_000, delta_inr=-1_400),
         "Mumbai: ₹1,400 more for this batch alone, but the joint plan earns more with that truck room and demand given to other stock."),
        (Alternative(market_id=None, market_name="Hold at hub", code="HOLD", net_inr=-16_800, delta_inr=41_400),
         "Hold at hub: -₹16,800, it would spoil there."),
    ],
)
def test_alternative_sentences(a, expected):
    assert alternative_sentence(decision(), a) == expected


def test_headline_expired_matches_the_prd_example():
    d = decision(alternatives=[alt("EXPIRED_ON_ARRIVAL", sale_h=31, limit_h=24)])
    assert headline(d) == "Pune, not Mumbai: Mumbai arrival 31h vs 26h shelf life left."


def test_headline_with_discount_and_lock():
    d = decision(discount=0.2, locked=True, alternatives=[alt("LOWER_NET", net_inr=21_000, delta_inr=3_600)])
    assert headline(d) == "Locked by the dispatcher. Pune, not Mumbai: ₹3,600 more net here. 20% off at Pune lifts demand to sell it."


def test_headline_single_market():
    assert headline(decision()) == "Pune: the only market buying tomato it can reach fresh."


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("INFEASIBLE_DEMAND", "Cannot be sold fresh: no market can have it on sale before it expires. Discount locally or salvage."),
        ("TOO_RISKY", "Held: at P10 shelf life (26h) and P90 travel no market gets it on sale in time, though the forecast (30h) says one might."),
        ("CARRY_OVER", "Kept for tomorrow: 30h of shelf life left, and today's truck room earns more on shorter-life stock."),
        ("NO_ROOM", "Held: no truck room or demand left at any market it can reach fresh."),
    ],
)
def test_hold_sentences(code, expected):
    d = decision(status="held", market_id=None, market_name=None, discount=None, hold_code=code, net_inr=-16_800)
    assert headline(d) == expected


def test_not_worth_shipping_cites_best_option():
    d = decision(
        status="held", market_id=None, market_name=None, discount=None, hold_code="NOT_WORTH_SHIPPING", net_inr=0.0,
        alternatives=[alt("LOWER_NET", net_inr=-2_300, delta_inr=2_300)],
    )
    assert headline(d) == "Held: shipping it loses more than it saves (best option Mumbai, -₹2,300 vs ₹0 at the hub)."
