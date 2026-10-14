"""Claim parity: the README quotes the same numbers as submission-facts.json, which is built from results/."""

import json
from pathlib import Path

from evaluation.facts import build
from explain.reasons import inr

ROOT = Path(__file__).resolve().parent.parent


def signed_kg(x: float) -> str:
    return f"{'−' if x < 0 else '+'}{abs(round(x)):,} kg"


def test_committed_facts_match_results():
    committed = json.loads((ROOT / "submission-facts.json").read_text())
    fresh = build(committed["urls"]["api"], committed["urls"]["console"])
    assert committed == fresh, "submission-facts.json is stale: run `python -m evaluation.facts`"


def test_readme_quotes_the_facts():
    facts = json.loads((ROOT / "submission-facts.json").read_text())
    readme = (ROOT / "README.md").read_text()
    h = facts["headline"]
    days = h["heldout_days"]
    expected = [
        f"+{inr(h['median_net_gain_inr'])}",
        f"+{inr(h['net_gain_iqr_inr'][0])} to +{inr(h['net_gain_iqr_inr'][1])}",
        f"{h['net_wins']} of {days}",
        signed_kg(h["median_spoiled_delta_kg"]),
        f"{h['spoiled_wins']} of {days}",
        f"+{h['median_fill_delta_pp']:.2f} pp",
        f"{h['fill_wins']} of {days}",
        f"{h['validator_violations']} constraint violations",
        f"+{inr(facts['lading_robust']['median_net_gain_inr'])}",
        inr(-facts["ablations"]["ablation-no-discount"]["median_net_delta_inr"]),
        f"{facts['fifo_heldout_validator_fails']} of {days}",
        facts["urls"]["console"],
        facts["urls"]["api"],
    ]
    missing = [e for e in expected if e not in readme]
    assert not missing, f"README is out of step with submission-facts.json: {missing}"
