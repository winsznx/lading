"""Named failure states (PRD section 9). Every error the product surfaces carries one of these."""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    SCHEMA_INVALID = "SCHEMA_INVALID"
    INFEASIBLE_DEMAND = "INFEASIBLE_DEMAND"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    SOLVER_UNAVAILABLE = "SOLVER_UNAVAILABLE"
    VALIDATOR_FAIL = "VALIDATOR_FAIL"
    NO_TRUCK = "NO_TRUCK"
    LOCK_INFEASIBLE = "LOCK_INFEASIBLE"
    SCENARIO_TOO_LARGE = "SCENARIO_TOO_LARGE"
    SCENARIO_NOT_FOUND = "SCENARIO_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"


class LadingError(Exception):
    def __init__(self, state: State, message: str, path: str | None = None) -> None:
        super().__init__(message)
        self.state = state
        self.message = message
        self.path = path

    def as_dict(self) -> dict[str, str | None]:
        return {"state": self.state.value, "message": self.message, "path": self.path}
