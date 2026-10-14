"""Write submission-facts.json: the one place the README, the console, the form and any film quote from.

Every value is read from results/ (produced by `make reproduce`) or from the deploy URLs passed in.
`tests/test_claim_parity.py` fails if the README quotes a headline number that differs from this file.

Usage: LADING_API_URL=... LADING_WEB_URL=... python -m evaluation.facts
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FACTS = ROOT / "submission-facts.json"


def lakh(x: float) -> str:
    return f"{x / 100000:.2f} lakh"


def build(api_url: str, web_url: str) -> dict[str, Any]:
    def load(name: str) -> Any:
        return json.loads((RESULTS / name).read_text())

    heldout, verdict, canonical = load("heldout.json"), load("verdict.json"), load("canonical.json")
    ablations, stress, controls, manifest = (
        load("ablations.json"),
        load("stress.json"),
        load("controls.json"),
        load("manifest.json"),
    )
    timings = load("timings.json")
    arm = heldout["headline_arm"]
    s = heldout["summary"][arm]
    n = len(heldout["seeds"])
    canon_l, canon_f = canonical["arms"][arm]["outcome"], canonical["arms"]["fefo"]["outcome"]
    return {
        "product": "Lading",
        "line": "Plans which produce goes where, when, and at what price, so less of it rots.",
        "urls": {"console": web_url, "api": api_url},
        "headline": {
            "arm": arm,
            "vs": "fefo",
            "heldout_days": n,
            "draws_per_day": heldout["draws_per_scenario"],
            "median_net_gain_inr": s["net_inr"]["median"],
            "net_gain_iqr_inr": [s["net_inr"]["q1"], s["net_inr"]["q3"]],
            "net_wins": s["net_inr"]["wins"],
            "median_spoiled_delta_kg": s["spoiled_kg"]["median"],
            "spoiled_delta_iqr_kg": [s["spoiled_kg"]["q1"], s["spoiled_kg"]["q3"]],
            "spoiled_wins": s["spoiled_kg"]["wins"],
            "median_fill_delta_pp": s["demand_filled_pct"]["median"],
            "fill_wins": s["demand_filled_pct"]["wins"],
            "validator_violations": heldout["validator"][arm]["violations"],
            "verdict": verdict["verdict"],
            "statement": verdict["statement"],
        },
        "canonical_run": {
            "seed": canonical["seed"],
            "scenario_id": canonical["scenario_id"],
            "draws": canonical["draws"],
            "lading": {k: canon_l[k] for k in ("spoiled_kg", "demand_filled_pct", "net_inr")},
            "fefo": {k: canon_f[k] for k in ("spoiled_kg", "demand_filled_pct", "net_inr")},
            "validator": canonical["arms"][arm]["validation"],
        },
        "lading_robust": {
            "median_net_gain_inr": heldout["summary"]["lading-robust"]["net_inr"]["median"],
            "net_wins": heldout["summary"]["lading-robust"]["net_inr"]["wins"],
            "median_spoiled_delta_kg": heldout["summary"]["lading-robust"]["spoiled_kg"]["median"],
            "spoiled_wins": heldout["summary"]["lading-robust"]["spoiled_kg"]["wins"],
        },
        "ablations": {
            name: {
                "median_net_delta_inr": a["net_inr"]["median"],
                "median_spoiled_delta_kg": a["spoiled_kg"]["median"],
                "plans_failing_validator": a["plans_failing_validator"],
                "violations": a["violations"],
            }
            for name, a in ablations["summary"].items()
        },
        "stress": {
            family: {
                "median_net_gain_inr": d["summary"][arm]["net_inr"]["median"],
                "net_wins": d["summary"][arm]["net_inr"]["wins"],
                "median_spoiled_delta_kg": d["summary"][arm]["spoiled_kg"]["median"],
                "spoiled_wins": d["summary"][arm]["spoiled_kg"]["wins"],
                "days": len(d["seeds"]),
            }
            for family, d in stress["families"].items()
        },
        "controls": {name: {"passed": c["passed"], "detail": c["detail"]} for name, c in controls.items()},
        "fifo_heldout_validator_fails": heldout["validator"]["fifo"]["fail"],
        "solve_time_median_s": timings["heldout"][arm]["median_s"],
        "manifest": {
            k: manifest[k]
            for k in ("commit", "frozen_at_commit", "cost_model_sha256", "planner_config_sha256", "host")
        },
        "synthetic": True,
        "data_note": "All scenarios are synthetic, from a disclosed seeded generator (docs/ASSUMPTIONS.md). Hub and mandi names are real places; every number attached to them is an assumption.",
    }


def main() -> None:
    facts = build(os.environ.get("LADING_API_URL", ""), os.environ.get("LADING_WEB_URL", ""))
    FACTS.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")
    h = facts["headline"]
    print(
        f"{h['arm']}: +INR {h['median_net_gain_inr']:,.0f} net ({h['net_wins']}/{h['heldout_days']}), "
        f"{h['median_spoiled_delta_kg']:+,.0f} kg spoiled ({h['spoiled_wins']}/{h['heldout_days']}), {h['verdict']}"
    )


if __name__ == "__main__":
    main()
