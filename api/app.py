"""Lading API.

Every plan request runs the real planner, FEFO, the independent validator and the simulator. There is
no cached demo answer and no fallback: if the solver can't produce a plan the response is a named error.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from api import curated
from api.ratelimit import RateLimiter
from api.schemas import (
    ArmResult,
    DisruptionInfo,
    Health,
    PlanRequest,
    PlanResponse,
    Reason,
    ReplanRequest,
    ReplanResponse,
    ScenarioInfo,
    SimulateRequest,
    ValidateRequest,
)
from baselines.fefo import plan_fefo
from errors import LadingError, State
from explain.reasons import alternative_sentence, headline
from explain.summary import plan_effect
from plan_model import Plan
from planner.decisions import Decision, build_decisions
from planner.milp import config as planner_config
from planner.milp import plan_lading
from planner.replan import apply, diff, effect_line
from scenarios.loader import parse
from scenarios.model import Scenario
from scenarios.tiny import batch, market
from scenarios.tiny import scenario as tiny_scenario
from sim.simulator import execute_many
from validate.validator import validate

log = logging.getLogger("lading.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(os.environ.get("LADING_RESULTS_DIR", ROOT / "results"))
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]
TRUSTED_PROXIES = [c.strip() for c in os.environ.get("TRUSTED_PROXIES", "127.0.0.1/32").split(",")]
COMMIT = os.environ.get("LADING_COMMIT", "dev")
HEADLINE_ARM = str(planner_config()["headline_arm"])

MAX_BATCHES, MAX_MARKETS, MAX_SLOTS, MAX_TRUCKS = 80, 10, 12, 10
_solve_slots = threading.BoundedSemaphore(int(os.environ.get("LADING_MAX_CONCURRENT_SOLVES", "2")))
limiter = RateLimiter(
    per_minute=float(os.environ.get("LADING_RATE_PER_MIN", "20")),
    burst=int(os.environ.get("LADING_RATE_BURST", "6")),
    trusted_proxies=TRUSTED_PROXIES,
)

app = FastAPI(title="Lading API", version="1.0.0", docs_url="/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
    max_age=600,
)

STATUS = {
    State.SCHEMA_INVALID: 422,
    State.SCENARIO_TOO_LARGE: 413,
    State.SCENARIO_NOT_FOUND: 404,
    State.LOCK_INFEASIBLE: 409,
    State.RATE_LIMITED: 429,
    State.SOLVER_TIMEOUT: 504,
    State.SOLVER_UNAVAILABLE: 503,
    State.VALIDATOR_FAIL: 500,
}


def _error(state: State, message: str, path: str | None = None, status: int | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status or STATUS.get(state, 400),
        content={"state": state.value, "message": message, "path": path},
    )


@app.exception_handler(LadingError)
async def _lading_error(_: Request, exc: LadingError) -> JSONResponse:
    return _error(exc.state, exc.message, exc.path)


@app.exception_handler(RequestValidationError)
async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    path = ".".join(str(p) for p in first["loc"] if p != "body")
    return _error(State.SCHEMA_INVALID, f"{path}: {first['msg']}", path)


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content={
            "state": "INTERNAL_ERROR",
            "message": "Something broke on our side. It has been logged.",
            "path": None,
        },
    )


def _rate_limit(request: Request) -> None:
    ok, wait = limiter.allow(limiter.client_ip(request))
    if not ok:
        raise LadingError(State.RATE_LIMITED, f"Too many plan requests. Try again in {wait:.0f} s.")


def _check_size(s: Scenario) -> None:
    for name, n, cap in (
        ("batches", len(s.batches), MAX_BATCHES),
        ("markets", len(s.markets), MAX_MARKETS),
        ("slots", len(s.slots), MAX_SLOTS),
        ("trucks", len(s.trucks), MAX_TRUCKS),
    ):
        if n > cap:
            raise LadingError(
                State.SCENARIO_TOO_LARGE, f"{n} {name}; the live planner takes at most {cap}.", path=name
            )


def _resolve(req: PlanRequest) -> Scenario:
    if (req.scenario_id is None) == (req.scenario is None):
        raise LadingError(
            State.SCHEMA_INVALID, "Send exactly one of scenario_id or scenario.", path="scenario_id"
        )
    s = curated.scenario(req.scenario_id) if req.scenario_id else parse(req.scenario)
    if req.controls is not None:
        raw = json.loads(s.model_dump_json())
        raw["controls"] = {**raw["controls"], **req.controls.model_dump(mode="json", exclude={"dispatched"})}
        s = parse(raw)
    _check_size(s)
    return s


def _as_json(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(model.model_dump_json())
    return data


def _arm(scenario: Scenario, plan: Plan, draws: int) -> ArmResult:
    report = validate(_as_json(scenario), _as_json(plan))
    return ArmResult(arm=plan.arm, plan=plan, validation=report, outcome=execute_many(scenario, plan, draws))


def _solve(scenario: Scenario, previous: Plan | None = None) -> Plan:
    if not _solve_slots.acquire(timeout=20):
        raise LadingError(
            State.SOLVER_UNAVAILABLE, "The planner is busy with other requests. Try again in a few seconds."
        )
    try:
        return plan_lading(scenario, HEADLINE_ARM, previous=previous)
    finally:
        _solve_slots.release()


def _reasons(decisions: list[Decision]) -> dict[str, Reason]:
    return {
        d.batch_id: Reason(
            headline=headline(d), alternatives=[alternative_sentence(d, a) for a in d.alternatives]
        )
        for d in decisions
    }


def _guard_valid(arm: ArmResult) -> None:
    if arm.validation["status"] != "PASS":
        first = arm.validation["violations"][0]
        log.error("validator rejected %s plan: %s", arm.arm, first)
        raise LadingError(
            State.VALIDATOR_FAIL,
            f"The independent validator rejected this plan: {first['message']} ({first['ref']}).",
        )


@app.get("/health", response_model=Health)
def health() -> Health:
    started = time.perf_counter()
    probe = tiny_scenario(
        [batch("b1", "tomato", 500, 20)], [market("m", 3, {"tomato": (20.0, 500)})], trucks=[1000]
    )
    plan = plan_lading(probe, "lading-point", time_limit_s=5)
    assert plan.solver is not None
    return Health(
        status="ok",
        version=app.version,
        commit=COMMIT,
        highs_version=plan.solver.highs_version,
        solver_check_s=round(time.perf_counter() - started, 3),
    )


@app.get("/scenarios", response_model=list[ScenarioInfo])
def scenarios() -> list[ScenarioInfo]:
    out = []
    for e in curated.index():
        s = curated.scenario(e["id"])
        out.append(
            ScenarioInfo(
                id=e["id"],
                label=e["label"],
                kind=e["kind"],
                note=e["note"],
                seed=s.seed,
                family=s.family,
                hub=s.hub.name,
                batches=len(s.batches),
                markets=len(s.markets),
                trucks=len(s.trucks),
                stock_kg=sum(b.kg for b in s.batches),
                live_verified=e.get("live_verified"),
                expected_solve_s=e.get("expected_solve_s"),
                disruptions=[
                    DisruptionInfo(index=i, kind=d.kind, label=d.label, at_slot=d.at_slot)
                    for i, d in enumerate(curated.disruptions(e["id"]))
                ],
            )
        )
    return out


@app.get("/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict[str, Any]:
    return _as_json(curated.scenario(scenario_id))


@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest, request: Request) -> PlanResponse:
    _rate_limit(request)
    started = time.perf_counter()
    s = _resolve(req)
    lading = _arm(s, _solve(s), req.draws)
    _guard_valid(lading)
    fefo = _arm(s, plan_fefo(s), req.draws)
    decisions = build_decisions(s, lading.plan)
    assert lading.plan.solver is not None
    return PlanResponse(
        scenario=_as_json(s),
        lading=lading,
        fefo=fefo,
        decisions=decisions,
        reasons=_reasons(decisions),
        effect=plan_effect(s, lading.plan, decisions),
        solve_s=lading.plan.solver.solve_s,
        elapsed_s=round(time.perf_counter() - started, 3),
    )


@app.post("/replan", response_model=ReplanResponse)
def replan(req: ReplanRequest, request: Request) -> ReplanResponse:
    _rate_limit(request)
    started = time.perf_counter()
    s = _resolve(req)
    if (req.disruption_index is None) == (req.disruption is None):
        raise LadingError(
            State.SCHEMA_INVALID, "Send exactly one of disruption_index or disruption.", path="disruption"
        )
    if req.disruption is not None:
        disruption = req.disruption
    else:
        if req.scenario_id is None:
            raise LadingError(
                State.SCHEMA_INVALID, "disruption_index needs a curated scenario_id.", path="disruption_index"
            )
        options = curated.disruptions(req.scenario_id)
        if req.disruption_index is None or req.disruption_index >= len(options):
            raise LadingError(
                State.SCHEMA_INVALID, "No such disruption for this scenario.", path="disruption_index"
            )
        disruption = options[req.disruption_index]

    previous = _solve(s)
    previous_fefo = plan_fefo(s)
    try:
        after = apply(s, previous, disruption)
        after_fefo = apply(s, previous_fefo, disruption)
    except ValueError as exc:
        raise LadingError(State.SCHEMA_INVALID, str(exc), path="disruption") from exc
    _check_size(after)
    new_plan = _solve(after, previous=previous)
    lading = _arm(after, new_plan, req.draws)
    _guard_valid(lading)
    fefo = _arm(after_fefo, plan_fefo(after_fefo), req.draws)
    decisions = build_decisions(after, new_plan)
    changes = diff(s, previous, after, new_plan, decisions)
    assert new_plan.solver is not None
    return ReplanResponse(
        scenario=_as_json(after),
        lading=lading,
        fefo=fefo,
        decisions=decisions,
        reasons=_reasons(decisions),
        effect=effect_line(disruption, after, changes, decisions),
        solve_s=new_plan.solver.solve_s,
        elapsed_s=round(time.perf_counter() - started, 3),
        disruption=disruption,
        changes=changes,
        previous_net_inr=previous.expected.net_inr,
    )


@app.post("/validate")
def validate_plan(req: ValidateRequest) -> dict[str, Any]:
    parse(req.scenario)
    try:
        return validate(req.scenario, req.plan)
    except (KeyError, TypeError) as exc:
        raise LadingError(
            State.SCHEMA_INVALID, f"plan is missing or mistyped field {exc}", path="plan"
        ) from exc


@app.post("/simulate")
def simulate(req: SimulateRequest, request: Request) -> dict[str, float]:
    _rate_limit(request)
    s = parse(req.scenario)
    _check_size(s)
    return execute_many(s, req.plan, req.draws)


RESULT_FILES = {
    "heldout.json",
    "ablations.json",
    "stress.json",
    "sensitivity.json",
    "manifest.json",
    "verdict.json",
    "controls.json",
    "tuning.json",
    "timings.json",
    "freeze.json",
    "canonical.json",
}


@app.get("/results/{name}")
def results(name: str) -> FileResponse:
    path = RESULTS_DIR / name
    if name not in RESULT_FILES or not path.is_file():
        raise LadingError(
            State.SCENARIO_NOT_FOUND, f"No results file '{name}'. Run `make reproduce`.", path=name
        )
    return FileResponse(path, media_type="application/json", headers={"cache-control": "public, max-age=300"})


@app.get("/assumptions")
def assumptions() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((ROOT / "scenarios" / "assumptions.json").read_text())
    return data


@app.get("/config")
def planner_settings() -> dict[str, Any]:
    return {"headline_arm": HEADLINE_ARM, "planner": planner_config()}
