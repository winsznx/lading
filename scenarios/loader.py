"""Load and check a scenario. Bad input is rejected with SCHEMA_INVALID and the exact field path."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError

from errors import LadingError, State
from scenarios.model import Scenario

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "scenario.json"


@cache
def _validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    return jsonschema.Draft202012Validator(schema)


def _json_path(parts: Any) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "$"


def _invalid(path: str, message: str) -> LadingError:
    return LadingError(State.SCHEMA_INVALID, f"{path}: {message}", path=path)


def parse(raw: Any) -> Scenario:
    errors = sorted(_validator().iter_errors(raw), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        raise _invalid(_json_path(first.absolute_path), first.message)
    try:
        scenario = Scenario.model_validate(raw)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        raise _invalid(_json_path(first_error["loc"]), first_error["msg"]) from exc
    check_references(scenario)
    return scenario


def load(path: Path) -> Scenario:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise _invalid("$", f"not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    return parse(raw)


def _unique(items: list[Any], field: str) -> None:
    seen: set[str] = set()
    for i, item in enumerate(items):
        if item.id in seen:
            raise _invalid(f"{field}[{i}].id", f"duplicate id '{item.id}'")
        seen.add(item.id)


def check_references(s: Scenario) -> None:
    for field in ("commodities", "batches", "markets", "trucks", "slots"):
        _unique(getattr(s, field), field)
    commodity_ids = {c.id for c in s.commodities}
    market_ids = {m.id for m in s.markets}
    batch_ids = {b.id for b in s.batches}
    slot_ids = {sl.id for sl in s.slots}
    truck_ids = {t.id for t in s.trucks}

    for i, b in enumerate(s.batches):
        if b.commodity_id not in commodity_ids:
            raise _invalid(f"batches[{i}].commodity_id", f"unknown commodity '{b.commodity_id}'")
    for i, m in enumerate(s.markets):
        seen: set[str] = set()
        for j, o in enumerate(m.offers):
            if o.commodity_id not in commodity_ids:
                raise _invalid(
                    f"markets[{i}].offers[{j}].commodity_id", f"unknown commodity '{o.commodity_id}'"
                )
            if o.commodity_id in seen:
                raise _invalid(f"markets[{i}].offers[{j}].commodity_id", "duplicate offer for commodity")
            seen.add(o.commodity_id)
    for i, sl in enumerate(s.slots):
        if sl.index != i:
            raise _invalid(f"slots[{i}].index", f"expected index {i}, slots must be listed in order")
        if i and sl.depart_h <= s.slots[i - 1].depart_h:
            raise _invalid(f"slots[{i}].depart_h", "departure times must strictly increase")
    levels = s.policy.discount_levels
    if levels[0] != 0 or any(b <= a for a, b in zip(levels, levels[1:], strict=False)):
        raise _invalid("policy.discount_levels", "must start at 0 and strictly increase")
    if s.policy.current_slot >= len(s.slots):
        raise _invalid("policy.current_slot", "no slot left to dispatch")

    ex = s.execution
    if ex.route_delay and ex.route_delay.market_id not in market_ids:
        raise _invalid("execution.route_delay.market_id", f"unknown market '{ex.route_delay.market_id}'")
    if ex.demand_shock and ex.demand_shock.market_id not in market_ids:
        raise _invalid("execution.demand_shock.market_id", f"unknown market '{ex.demand_shock.market_id}'")
    if ex.truck_loss and ex.truck_loss.truck_id not in truck_ids:
        raise _invalid("execution.truck_loss.truck_id", f"unknown truck '{ex.truck_loss.truck_id}'")

    for i, lock in enumerate(s.controls.locks):
        if lock.batch_id not in batch_ids:
            raise _invalid(f"controls.locks[{i}].batch_id", f"unknown batch '{lock.batch_id}'")
        if lock.market_id not in market_ids:
            raise _invalid(f"controls.locks[{i}].market_id", f"unknown market '{lock.market_id}'")
        if lock.slot_id not in slot_ids:
            raise _invalid(f"controls.locks[{i}].slot_id", f"unknown slot '{lock.slot_id}'")
    current = s.policy.current_slot
    for i, leg in enumerate(s.controls.dispatched):
        if leg.batch_id not in batch_ids or leg.market_id not in market_ids or leg.slot_id not in slot_ids:
            raise _invalid(f"controls.dispatched[{i}]", "unknown batch, market or slot")
        if s.slot(leg.slot_id).index >= current:
            raise _invalid(
                f"controls.dispatched[{i}].slot_id", "dispatched stock must have left before current_slot"
            )
    for i, veto in enumerate(s.controls.vetoes):
        if veto.batch_id not in batch_ids:
            raise _invalid(f"controls.vetoes[{i}].batch_id", f"unknown batch '{veto.batch_id}'")
        if veto.market_id not in market_ids:
            raise _invalid(f"controls.vetoes[{i}].market_id", f"unknown market '{veto.market_id}'")
