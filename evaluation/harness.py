"""Evaluation harness. `make reproduce` runs this end to end.

Order, as pre-registered in docs/GATES.md:

1. tuning set, seeds 0-19 (the only data any planner config change may use);
2. freeze check: the planner config must hash to what `results/freeze.json` recorded;
3. held-out set, seeds 1000-1049, generated now, after the freeze (plus organizer scenarios, if any,
   as a separate group);
4. stress families, ablations A1 and A2, elasticity sensitivity, controls P2/P3/P4/P6 and a no-op;
5. manifest and the automatic PRD section 4 falsifier verdict.

Every arm on a scenario sees the same scenario, forecast, cost model, simulator, validator and the same
realized draws. Usage: python -m evaluation.harness {tune|freeze|reproduce} [--small] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from api import curated
from baselines.fefo import plan_fefo
from baselines.fifo import plan_fifo
from evaluation.stats import METRICS, describe, summarise
from plan_assembly import assemble
from plan_model import Plan
from planner.milp import ABLATIONS, CONFIG_PATH, LADING_ARMS, config, plan_lading
from scenarios import organizer
from scenarios.model import Scenario
from scenarios.scenario_gen import ASSUMPTIONS_PATH, assumptions, dump, generate
from sim.draws import realize
from sim.simulator import DEFAULT_DRAWS, execute, execute_many
from validate.validator import validate

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "scenarios" / "generated"

TUNING = list(range(0, 20))
HELDOUT = list(range(1000, 1050))
STRESS_FAMILIES = ("demand_shock", "route_delay", "truck_loss", "wide_shelf")
STRESS = {f: list(range(2000 + 10 * i, 2010 + 10 * i)) for i, f in enumerate(STRESS_FAMILIES)}
HEALTHY = list(range(3000, 3005))
INFEASIBLE = list(range(3100, 3105))
CANONICAL_SEED = 1007
ELASTICITY_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)
BASE_ARMS = ("fifo", "fefo", *LADING_ARMS)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write(out: Path, name: str, data: Any) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(_json(data))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_arm(scenario: Scenario, arm: str) -> Plan:
    if arm == "fifo":
        return plan_fifo(scenario)
    if arm == "fefo":
        return plan_fefo(scenario)
    if arm == "no-op":
        return assemble(scenario, "no-op", "none", [], {})
    cfg = config()
    return plan_lading(scenario, arm, time_limit_s=cfg["eval_time_limit_s"])


def _metrics(scenario: Scenario, plan: Plan, draws: int) -> dict[str, Any]:
    outcome = execute_many(scenario, plan, draws)
    report = validate(json.loads(scenario.model_dump_json()), json.loads(plan.model_dump_json()))
    row: dict[str, Any] = {
        "spoiled_kg": outcome["spoiled_kg"],
        "demand_filled_pct": outcome["demand_filled_pct"],
        "net_inr": outcome["net_inr"],
        "unmet_demand_kg": outcome["unmet_demand_kg"],
        "expired_in_transit_kg": outcome["expired_in_transit_kg"],
        "unsold_kg": outcome["unsold_kg"],
        "hub_spoiled_kg": outcome["hub_spoiled_kg"],
        "carry_over_kg": outcome["carry_over_kg"],
        "validator": report["status"],
        "violations": report["violation_count"],
    }
    if plan.solver is not None:
        row["gap"] = plan.solver.gap
        row["solver_status"] = plan.solver.status
    return row


def _delta(arms: dict[str, dict[str, Any]], arm: str, ref: str) -> dict[str, float]:
    return {m: round(arms[arm][m] - arms[ref][m], 2) for m in METRICS}


def _save(scenario: Scenario, group: str) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / f"{group}-{scenario.id}.json").write_text(dump(scenario))


def run_scenario(job: dict[str, Any]) -> dict[str, Any]:
    """Plan, validate and execute every requested arm on one scenario. Runs in a worker process."""
    scenario = Scenario.model_validate_json(job["scenario"])
    draws = job["draws"]
    plans = {arm: plan_arm(scenario, arm) for arm in job["arms"]}
    arms = {arm: _metrics(scenario, plan, draws) for arm, plan in plans.items()}
    row: dict[str, Any] = {
        "seed": scenario.seed,
        "scenario_id": scenario.id,
        "hub": scenario.hub.name,
        "batches": len(scenario.batches),
        "stock_kg": sum(b.kg for b in scenario.batches),
        "infeasible_batches": len(plans[job["arms"][0]].infeasible),
        "arms": arms,
    }
    timings = {arm: p.solver.solve_s for arm, p in plans.items() if p.solver is not None}
    sensitivity = {}
    for factor in job.get("elasticity_factors", ()):
        shocked = scenario.model_copy(
            update={"execution": scenario.execution.model_copy(update={"elasticity_factor": factor})}
        )
        sensitivity[str(factor)] = {
            arm: {k: v for k, v in execute_many(shocked, plans[arm], draws).items() if k in METRICS}
            for arm in job["sensitivity_arms"]
        }
    return {"row": row, "timings": timings, "sensitivity": sensitivity}


def _pool_map(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workers = int(os.environ.get("LADING_WORKERS", max(1, (os.cpu_count() or 2) - 1)))
    if workers == 1:
        return [run_scenario(j) for j in jobs]
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(run_scenario, jobs))


def _job(scenario: Scenario, arms: tuple[str, ...], draws: int, **extra: Any) -> dict[str, Any]:
    return {"scenario": scenario.model_dump_json(), "arms": list(arms), "draws": draws, **extra}


def _group(
    results: list[dict[str, Any]], compare: tuple[str, ...], ref: str = "fefo"
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for r in results:
        row = r["row"]
        row["delta"] = {arm: _delta(row["arms"], arm, ref) for arm in compare}
        rows.append(row)
    summary = {arm: summarise(rows, arm) for arm in compare}
    return rows, summary


def _validator_summary(rows: list[dict[str, Any]], arms: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {
        arm: {
            "pass": sum(1 for r in rows if r["arms"][arm]["validator"] == "PASS"),
            "fail": sum(1 for r in rows if r["arms"][arm]["validator"] != "PASS"),
            "violations": sum(int(r["arms"][arm]["violations"]) for r in rows),
        }
        for arm in arms
    }


def _timing_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    arms = sorted({a for r in results for a in r["timings"]})
    for arm in arms:
        values = np.array([r["timings"][arm] for r in results if arm in r["timings"]])
        out[arm] = {
            "median_s": round(float(np.median(values)), 3),
            "p90_s": round(float(np.percentile(values, 90)), 3),
            "max_s": round(float(values.max()), 3),
            "n": int(values.size),
        }
    return out


def tune(seeds: list[int], draws: int) -> dict[str, Any]:
    scenarios = [generate(s) for s in seeds]
    results = _pool_map([_job(s, BASE_ARMS, draws) for s in scenarios])
    rows, summary = _group(results, ("fifo", *LADING_ARMS))
    best = max(LADING_ARMS, key=lambda arm: (summary[arm]["net_inr"]["median"], arm == "lading-robust"))
    return {
        "seeds": seeds,
        "draws_per_scenario": draws,
        "rule": "headline arm = the Lading arm with the higher median paired net INR gain vs FEFO on the tuning seeds",
        "recommended_headline_arm": best,
        "summary": summary,
        "rows": rows,
        "timings": _timing_summary(results),
    }


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def code_commit() -> str:
    return _git(
        "log",
        "-1",
        "--format=%H",
        "--",
        ".",
        ":(exclude)results",
        ":(exclude)docs",
        ":(exclude)README.md",
        ":(exclude)submission-facts.json",
        ":(exclude)scenarios/curated/index.json",
    )


def code_dirty() -> bool:
    status = _git(
        "status",
        "--porcelain",
        "--",
        ".",
        ":(exclude)results",
        ":(exclude)docs",
        ":(exclude)README.md",
        ":(exclude)submission-facts.json",
        ":(exclude)scenarios/curated/index.json",
        ":(exclude).ci-results",
    )
    return bool(status) and status != "unknown"


def freeze(out: Path) -> dict[str, Any]:
    tuning_path = out / "tuning.json"
    if not tuning_path.exists():
        sys.exit("run `python -m evaluation.harness tune` first")
    tuning_data = json.loads(tuning_path.read_text())
    headline = config()["headline_arm"]
    if headline != tuning_data["recommended_headline_arm"]:
        sys.exit(
            f"planner/config.json headline_arm is {headline}, the tuning rule picked {tuning_data['recommended_headline_arm']}"
        )
    record = {
        "planner_config_sha256": _sha256(CONFIG_PATH),
        "cost_model_sha256": _sha256(ROOT / "cost_model.py"),
        "headline_arm": headline,
        "frozen_at_commit": code_commit(),
        "tuning_seeds": tuning_data["seeds"],
        "heldout_seeds": HELDOUT,
        "stress_seeds": STRESS,
        "rule": tuning_data["rule"],
    }
    _write(out, "freeze.json", record)
    return record


def _check_freeze(out: Path) -> dict[str, Any]:
    path = ROOT / "results" / "freeze.json"
    if not path.exists():
        sys.exit(
            "no results/freeze.json: run tune, set headline_arm, commit, then freeze before the held-out run"
        )
    record: dict[str, Any] = json.loads(path.read_text())
    if record["planner_config_sha256"] != _sha256(CONFIG_PATH):
        sys.exit("planner/config.json changed after the freeze; the held-out run would not be clean")
    if out != ROOT / "results":
        _write(out, "freeze.json", record)
    return record


def controls(draws: int, small: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    headline = str(config()["headline_arm"])

    healthy = [generate(s, "healthy") for s in (HEALTHY[:2] if small else HEALTHY)]
    rows = [r["row"] for r in _pool_map([_job(s, ("fefo", headline), draws) for s in healthy])]
    spoil_share = max(
        max(r["arms"][a]["spoiled_kg"] for a in ("fefo", headline)) / r["stock_kg"] for r in rows
    )
    net_gap = max(
        abs(r["arms"][headline]["net_inr"] - r["arms"]["fefo"]["net_inr"]) / r["arms"]["fefo"]["net_inr"]
        for r in rows
    )
    out["p2_healthy"] = {
        "passed": bool(spoil_share < 0.02 and net_gap < 0.03),
        "rule": "ample shelf life, trucks and demand: both arms spoil < 2% of stock and net INR within 3% of each other",
        "max_spoiled_share": round(spoil_share, 4),
        "max_net_gap_share": round(net_gap, 4),
        "detail": f"max spoilage {spoil_share:.1%} of stock, max net gap {net_gap:.1%} across {len(rows)} healthy days",
        "rows": rows,
    }

    infeasible = [generate(s, "infeasible") for s in (INFEASIBLE[:2] if small else INFEASIBLE)]
    p3: list[dict[str, Any]] = []
    for s in infeasible:
        stuck = {b.id for b in s.batches if b.shelf_life_h <= 3.0}
        plans = {arm: plan_arm(s, arm) for arm in ("fefo", headline)}
        flagged = {arm: sorted(p.infeasible) for arm, p in plans.items()}
        shipped = {arm: sorted({sh.batch_id for sh in p.shipments} & stuck) for arm, p in plans.items()}
        p3.append(
            {
                "scenario_id": s.id,
                "stuck": sorted(stuck),
                "flagged": flagged,
                "shipped_anyway": shipped,
                "stuck_kg": sum(b.kg for b in s.batches if b.id in stuck),
            }
        )
    ok = all(
        set(r["flagged"][a]) == set(r["stuck"]) and not r["shipped_anyway"][a]
        for r in p3
        for a in ("fefo", headline)
    )
    out["p3_infeasible"] = {
        "passed": ok,
        "rule": "batches no market can receive fresh are flagged INFEASIBLE_DEMAND, never shipped, and spoil equally in every arm",
        "detail": f"{sum(len(r['stuck']) for r in p3)} stuck batches over {len(p3)} days, all flagged and held by both arms"
        if ok
        else "a stuck batch was missed or shipped",
        "rows": p3,
    }

    p4 = curated.scenario("p4-far-market")
    p4_plans = {arm: plan_arm(p4, arm) for arm in ("fifo", "fefo", headline)}
    far = "delhi_azadpur"
    reachable = {b.id for b in p4.batches if b.shelf_life_h - p4.policy.safety_margin_h >= 0 + 22 + 3}
    sent = {
        arm: sorted({sh.batch_id for sh in p.shipments if sh.market_id == far}) for arm, p in p4_plans.items()
    }
    p4_metrics = {arm: _metrics(p4, p, draws) for arm, p in p4_plans.items()}
    out["p4_harmful"] = {
        "passed": bool(
            set(sent[headline]) <= reachable
            and p4_metrics["fifo"]["expired_in_transit_kg"] > 0
            and p4_metrics["fifo"]["validator"] == "FAIL"
            and p4_metrics[headline]["validator"] == "PASS"
        ),
        "rule": "the highest-price market is too far for short-life stock: Lading refuses it, FIFO falls for it and spoils",
        "sent_to_far_market": sent,
        "can_reach_far_market_fresh": sorted(reachable),
        "arms": p4_metrics,
        "detail": f"{headline} sends {len(sent[headline])} batches to Delhi, all able to arrive fresh; FIFO sends "
        f"{len(sent['fifo'])} and loses {p4_metrics['fifo']['expired_in_transit_kg']:,.0f} kg in transit",
    }

    canonical = generate(CANONICAL_SEED)
    digests = []
    for _ in range(2):
        plan = plan_arm(canonical, headline)
        outcome = execute_many(canonical, plan, draws)
        digests.append(
            hashlib.sha256(
                (plan.model_dump_json(exclude={"solver": {"solve_s"}}) + _json(outcome)).encode()
            ).hexdigest()
        )
    out["p6_replay"] = {
        "passed": digests[0] == digests[1],
        "rule": "same seed twice gives a byte-identical plan (solve time excluded) and identical outcomes",
        "sha256": digests,
        "detail": "identical" if digests[0] == digests[1] else "replay differed",
    }

    noop_rows = []
    for seed in HELDOUT[:2] if small else HELDOUT[:10]:
        s = generate(seed)
        plan = plan_arm(s, "no-op")
        for d in range(3):
            real = realize(s, d)
            sim = execute(s, plan, real)
            expect = sum(b.kg for b in s.batches if real.shelf_h[b.id] <= s.policy.horizon_h)
            noop_rows.append(
                {
                    "seed": seed,
                    "draw": d,
                    "sim_spoiled_kg": round(sim.spoiled_kg, 2),
                    "independent_kg": round(expect, 2),
                }
            )
    out["no_op"] = {
        "passed": all(abs(r["sim_spoiled_kg"] - r["independent_kg"]) < 1e-6 for r in noop_rows),
        "rule": "dispatch nothing: simulated spoilage equals the kg whose realized shelf life ends inside the horizon, counted independently",
        "detail": f"{len(noop_rows)} scenario-draws checked",
        "rows": noop_rows,
    }
    return out


def reproduce(out: Path, small: bool, draws: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    print("[1/6] tuning set", flush=True)
    tuning = tune(TUNING[:3] if small else TUNING, draws)
    _write(out, "tuning.json", tuning)

    print("[2/6] freeze check", flush=True)
    frozen = _check_freeze(out)
    headline = frozen["headline_arm"]

    print("[3/6] held-out set (generated now, after the freeze)", flush=True)
    seeds = HELDOUT[:5] if small else HELDOUT
    heldout_scenarios = [generate(s) for s in seeds]
    for s in heldout_scenarios:
        _save(s, "heldout")
    arms = (*BASE_ARMS, *ABLATIONS)
    results = _pool_map(
        [
            _job(s, arms, draws, elasticity_factors=ELASTICITY_FACTORS, sensitivity_arms=["fefo", headline])
            for s in heldout_scenarios
        ]
    )
    ablation_results = json.loads(json.dumps(results))
    rows, summary = _group(results, ("fifo", *LADING_ARMS))
    for r in rows:
        r["arms"] = {a: r["arms"][a] for a in BASE_ARMS}
    heldout = {
        "headline_arm": headline,
        "draws_per_scenario": draws,
        "seeds": seeds,
        "arms": list(BASE_ARMS),
        "rows": rows,
        "summary": summary,
        "validator": _validator_summary(rows, BASE_ARMS),
    }
    organizer_scenarios = organizer.load_all() if organizer.available() else []
    if organizer_scenarios:
        org_rows, org_summary = _group(
            _pool_map([_job(s, BASE_ARMS, draws) for s in organizer_scenarios]), ("fifo", *LADING_ARMS)
        )
        heldout["organizer"] = {"rows": org_rows, "summary": org_summary}
    _write(out, "heldout.json", heldout)

    ab_rows = []
    for r in ablation_results:
        row = r["row"]
        row["arms"] = {a: row["arms"][a] for a in (headline, *ABLATIONS)}
        row["delta"] = {a: _delta(row["arms"], a, headline) for a in ABLATIONS}
        ab_rows.append(row)
    ablations = {
        "base_arm": headline,
        "rows": ab_rows,
        "summary": {
            a: {
                "vs": headline,
                **summarise(ab_rows, a),
                "violations": sum(int(r["arms"][a]["violations"]) for r in ab_rows),
                "plans_failing_validator": sum(1 for r in ab_rows if r["arms"][a]["validator"] != "PASS"),
            }
            for a in ABLATIONS
        },
    }
    _write(out, "ablations.json", ablations)

    points = []
    for factor in ELASTICITY_FACTORS:
        deltas = {
            m: [
                r["sensitivity"][str(factor)][headline][m] - r["sensitivity"][str(factor)]["fefo"][m]
                for r in results
            ]
            for m in METRICS
        }
        points.append({"factor": factor, **{m: describe(v, m) for m, v in deltas.items()}})
    _write(
        out,
        "sensitivity.json",
        {
            "arm": headline,
            "factors": list(ELASTICITY_FACTORS),
            "note": "Plans are fixed; realized elasticity = disclosed elasticity x factor. Deltas are arm minus FEFO.",
            "points": points,
        },
    )

    print("[4/6] stress families", flush=True)
    families = {}
    stress_timings = []
    for family, fam_seeds in STRESS.items():
        fam_seeds = fam_seeds[:2] if small else fam_seeds
        scenarios = [generate(s, family) for s in fam_seeds]
        for s in scenarios:
            _save(s, "stress")
        res = _pool_map([_job(s, ("fefo", *LADING_ARMS), draws) for s in scenarios])
        stress_timings += res
        fam_rows, fam_summary = _group(res, LADING_ARMS)
        families[family] = {
            "description": assumptions()["families"][family],
            "seeds": fam_seeds,
            "summary": fam_summary,
            "validator": _validator_summary(fam_rows, ("fefo", *LADING_ARMS)),
            "rows": fam_rows,
        }
    _write(out, "stress.json", {"families": families, "draws_per_scenario": draws})

    print("[5/6] controls and canonical run", flush=True)
    _write(out, "controls.json", controls(draws, small))
    canonical = generate(CANONICAL_SEED)
    canon = {}
    for arm in ("fefo", headline):
        plan = plan_arm(canonical, arm)
        report = validate(json.loads(canonical.model_dump_json()), json.loads(plan.model_dump_json()))
        canon[arm] = {
            "outcome": execute_many(canonical, plan, draws),
            "expected": plan.expected.model_dump(),
            "validation": {"status": report["status"], "violation_count": report["violation_count"]},
            "shipments": len(plan.shipments),
            "held": len(plan.held),
        }
    _write(
        out,
        "canonical.json",
        {"scenario_id": canonical.id, "seed": CANONICAL_SEED, "draws": draws, "arms": canon},
    )
    _write(
        out,
        "timings.json",
        {
            "note": "Wall-clock solve times on the machine that ran make reproduce. Excluded from the byte-identical replay check.",
            "heldout": _timing_summary(results),
            "stress": _timing_summary(stress_timings),
            "tuning": tuning["timings"],
        },
    )

    print("[6/6] manifest and verdict", flush=True)
    libs = {
        name: metadata.version(name) for name in ("highspy", "numpy", "pydantic", "fastapi", "jsonschema")
    }
    _write(
        out,
        "manifest.json",
        {
            "commit": code_commit(),
            "dirty": code_dirty(),
            "frozen_at_commit": frozen["frozen_at_commit"],
            "seeds": {
                "tuning": tuning["seeds"],
                "heldout": seeds,
                "stress": {f: (s[:2] if small else s) for f, s in STRESS.items()},
                "healthy": HEALTHY,
                "infeasible": INFEASIBLE,
                "canonical": CANONICAL_SEED,
            },
            "draws_per_scenario": draws,
            "exec_seed_stream": "SeedSequence([scenario seed, 202, draw, kind])",
            "solver": {
                "name": "HiGHS",
                "version": libs["highspy"],
                "mip_rel_gap": config()["mip_rel_gap"],
                "threads": config()["threads"],
            },
            "cost_model_sha256": _sha256(ROOT / "cost_model.py"),
            "planner_config_sha256": _sha256(CONFIG_PATH),
            "assumptions_sha256": _sha256(ASSUMPTIONS_PATH),
            "python": platform.python_version(),
            "libraries": libs,
            "host": f"{platform.system()} {platform.machine()}",
            "small": small,
        },
    )
    s = summary[headline]
    violations = heldout["validator"][headline]["violations"]
    triggered = s["net_inr"]["median"] <= 0 or s["spoiled_kg"]["median"] > 0
    statement = (
        f"On {len(seeds)} held-out days, {headline} vs FEFO: median paired net gain INR {s['net_inr']['median']:,.0f} "
        f"(wins {s['net_inr']['wins']}/{len(seeds)}), median spoiled kg change {s['spoiled_kg']['median']:+,.0f} "
        f"(fewer in {s['spoiled_kg']['wins']}/{len(seeds)}), median demand filled change {s['demand_filled_pct']['median']:+.2f} pp, "
        f"{violations} validator violations."
    )
    _write(
        out,
        "verdict.json",
        {
            "headline_arm": headline,
            "falsifier": "median paired net-revenue gain <= 0, or median spoilage higher than FEFO (PRD section 4)",
            "median_net_gain_inr": s["net_inr"]["median"],
            "median_spoiled_delta_kg": s["spoiled_kg"]["median"],
            "median_fill_delta_pp": s["demand_filled_pct"]["median"],
            "validator_violations": violations,
            "triggered": triggered,
            "verdict": "WITHDRAWN" if triggered else "HOLDS",
            "statement": (
                "Falsifier triggered: the 'beats FEFO' headline is withdrawn. " if triggered else ""
            )
            + statement,
        },
    )
    print(statement, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=("tune", "freeze", "reproduce"))
    parser.add_argument("--small", action="store_true", help="a few seeds per group, for CI")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.command == "tune":
        data = tune(TUNING[:3] if args.small else TUNING, args.draws)
        _write(out, "tuning.json", data)
        print(f"tuning rule picks {data['recommended_headline_arm']}")
        for arm, summ in data["summary"].items():
            print(arm, {m: (summ[m]["median"], summ[m]["wins"]) for m in METRICS})
    elif args.command == "freeze":
        print(_json(freeze(out)))
    else:
        reproduce(out, args.small, args.draws)


if __name__ == "__main__":
    main()
