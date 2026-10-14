"""The curated scenarios a judge picks from. Each one is a real scenario, planned live on request."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from errors import LadingError, State
from planner.replan import Disruption
from scenarios.loader import load
from scenarios.model import Scenario
from scenarios.scenario_gen import generate

CURATED_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "curated"
INDEX_PATH = CURATED_DIR / "index.json"


@cache
def index() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads(INDEX_PATH.read_text())["scenarios"]
    return entries


def entry(scenario_id: str) -> dict[str, Any]:
    found = next((e for e in index() if e["id"] == scenario_id), None)
    if found is None:
        raise LadingError(
            State.SCENARIO_NOT_FOUND, f"No curated scenario '{scenario_id}'.", path="scenario_id"
        )
    return found


@cache
def scenario(scenario_id: str) -> Scenario:
    e = entry(scenario_id)
    if "generator" in e:
        gen = e["generator"]
        return generate(int(gen["seed"]), gen.get("family", "base"))
    return load(CURATED_DIR / e["file"])


def disruptions(scenario_id: str) -> list[Disruption]:
    return [Disruption.model_validate(d) for d in entry(scenario_id).get("disruptions", [])]
