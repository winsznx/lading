"""Organizer data adapter.

PRD section 6, case 1: if the organizers publish scenarios they become the primary input and the
generator becomes secondary. Files dropped into `data/organizer/` are picked up here. A file already in
the Lading schema loads directly. Any other structure needs a converter registered in CONVERTERS, so an
unknown format fails loudly with SCHEMA_INVALID instead of being guessed at.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from errors import LadingError, State
from scenarios.loader import parse
from scenarios.model import SCHEMA_VERSION, Scenario

ORGANIZER_DIR = Path(__file__).resolve().parent.parent / "data" / "organizer"

Converter = Callable[[dict[str, Any]], dict[str, Any]]
CONVERTERS: dict[str, Converter] = {}


def available(directory: Path = ORGANIZER_DIR) -> bool:
    return any(directory.glob("*.json"))


def _to_lading(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    if raw.get("schema_version") == SCHEMA_VERSION:
        return raw
    fmt = raw.get("format")
    if isinstance(fmt, str) and fmt in CONVERTERS:
        return CONVERTERS[fmt](raw)
    raise LadingError(
        State.SCHEMA_INVALID,
        f"{path.name}: unrecognised organizer format; add a converter in scenarios/organizer.py",
        path="$",
    )


def load_all(directory: Path = ORGANIZER_DIR) -> list[Scenario]:
    scenarios = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text())
        scenario = parse(_to_lading(raw, path))
        if scenario.source != "organizer":
            raise LadingError(State.SCHEMA_INVALID, f"{path.name}: source must be 'organizer'", path="source")
        scenarios.append(scenario)
    return scenarios
