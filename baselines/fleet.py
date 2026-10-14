"""Truck bookkeeping for the greedy baselines.

A truck serves one market per trip and is away for the round trip (2 x travel + turnaround buffer).
Several trucks can serve the same market in the same slot. Batches split across them freely.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from scenarios.model import Market, Slot
from world import World

Cell = tuple[str, str]


@dataclass
class Fleet:
    world: World
    trips: dict[str, list[tuple[float, float]]] = field(default_factory=lambda: defaultdict(list))
    trucks_by_cell: dict[Cell, list[str]] = field(default_factory=lambda: defaultdict(list))
    load_by_cell: dict[Cell, float] = field(default_factory=lambda: defaultdict(float))

    def _capacity(self, truck_id: str) -> float:
        return next(t.capacity_kg for t in self.world.scenario.trucks if t.id == truck_id)

    def spare(self, market: Market, slot: Slot) -> float:
        cell = (market.id, slot.id)
        return sum(self._capacity(t) for t in self.trucks_by_cell[cell]) - self.load_by_cell[cell]

    def _free(self, truck_id: str, market: Market, slot: Slot) -> bool:
        if not self.world.truck_available(truck_id, slot):
            return False
        start, end = slot.depart_h, slot.depart_h + self.world.round_trip_h(market)
        return all(end <= s or e <= start for s, e in self.trips[truck_id])

    def plan_room(self, market: Market, slot: Slot, kg: float) -> list[str] | None:
        """Trucks to add so `kg` more fits in this cell, or None if it can't. [] means it fits already."""
        short = kg - self.spare(market, slot)
        if short <= 1e-9:
            return []
        free = [t for t in self.world.scenario.trucks if self._free(t.id, market, slot)]
        added: list[str] = []
        # Smallest single truck that covers the shortfall, else the largest and keep going.
        while short > 1e-9 and free:
            covering = [t for t in free if t.capacity_kg >= short]
            pick = min(covering, key=lambda t: (t.capacity_kg, t.id)) if covering else max(free, key=lambda t: (t.capacity_kg, t.id))
            added.append(pick.id)
            short -= pick.capacity_kg
            free.remove(pick)
        return added if short <= 1e-9 else None

    def load(self, market: Market, slot: Slot, kg: float, add_trucks: list[str]) -> None:
        cell = (market.id, slot.id)
        for truck_id in add_trucks:
            self.trips[truck_id].append((slot.depart_h, slot.depart_h + self.world.round_trip_h(market)))
            self.trucks_by_cell[cell].append(truck_id)
        self.load_by_cell[cell] += kg
