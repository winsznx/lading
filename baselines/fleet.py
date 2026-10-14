"""Truck room for the greedy baselines.

Trucks are hired per slot, so each slot has the fleet's capacity (minus trucks out of service).
A batch fills the earliest slots it can still use, splitting across them if one slot can't take it all.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from scenarios.model import Slot
from world import World


@dataclass
class Fleet:
    world: World
    load: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def spare(self, slot: Slot) -> float:
        return self.world.slot_capacity_kg(slot) - self.load[slot.id]

    def fit(self, slots: list[Slot], kg: float) -> list[tuple[Slot, float]] | None:
        """Earliest-first split of `kg` over `slots`, or None if they can't take all of it."""
        out: list[tuple[Slot, float]] = []
        left = kg
        for s in slots:
            take = min(left, max(self.spare(s), 0.0))
            if take > 1e-9:
                out.append((s, take))
                left -= take
            if left <= 1e-9:
                return out
        return None

    def take(self, parts: list[tuple[Slot, float]]) -> None:
        for s, kg in parts:
            self.load[s.id] += kg
