"""Typed request and response bodies for the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from plan_model import Plan
from planner.decisions import Decision
from planner.replan import Change, Disruption
from scenarios.model import Controls


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    commit: str
    highs_version: str
    solver_check_s: float


class DisruptionInfo(BaseModel):
    index: int
    kind: str
    label: str
    at_slot: int


class ScenarioInfo(BaseModel):
    id: str
    label: str
    kind: str
    note: str
    seed: int | None
    family: str
    hub: str
    batches: int
    markets: int
    trucks: int
    stock_kg: float
    live_verified: str | None
    expected_solve_s: float | None
    disruptions: list[DisruptionInfo]


class PlanRequest(Strict):
    scenario_id: str | None = Field(default=None, description="A curated scenario id.")
    scenario: dict[str, Any] | None = Field(default=None, description="A full scenario in the Lading schema.")
    controls: Controls | None = Field(default=None, description="Dispatcher locks and vetoes to apply.")
    draws: int = Field(default=30, ge=1, le=50)


class ReplanRequest(PlanRequest):
    disruption_index: int | None = Field(
        default=None, ge=0, description="One of the scenario's curated disruptions."
    )
    disruption: Disruption | None = None


class ValidateRequest(Strict):
    scenario: dict[str, Any]
    plan: Plan


class SimulateRequest(Strict):
    scenario: dict[str, Any]
    plan: Plan
    draws: int = Field(default=30, ge=1, le=50)


class Reason(BaseModel):
    headline: str
    alternatives: list[str]


class ArmResult(BaseModel):
    arm: str
    plan: Plan
    validation: dict[str, Any]
    outcome: dict[str, float]


class PlanResponse(BaseModel):
    solver_state: Literal["OPTIMAL", "SOLVER_TIMEOUT"] = Field(
        description="SOLVER_TIMEOUT: the live time budget ran out; the plan is the best one found, gap in lading.plan.solver.gap."
    )
    scenario: dict[str, Any]
    lading: ArmResult
    fefo: ArmResult
    decisions: list[Decision]
    reasons: dict[str, Reason]
    effect: str
    solve_s: float
    elapsed_s: float


class ReplanResponse(PlanResponse):
    disruption: Disruption
    changes: list[Change]
    previous_net_inr: float
