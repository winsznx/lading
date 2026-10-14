"""Lading's planner: one mixed-integer program over batch x market x slot, with the price per commodity
per market picked from the discount ladder inside the same program.

Variables
  x[b,m]    1 if batch b goes to market m. Only created when b can still be on sale at m before expiry
            minus the safety margin from some open slot (the hard shelf-life constraint), unless the
            soft-shelf ablation is running.
  y[m,c,l]  1 if commodity c sells at market m at discount level l. Exactly one level per cell.
  q[m,c,l]  kg of c sold at m at level l, at most demand x (1 + elasticity x discount) when chosen.

Slots enter through deadlines. A batch going to m must leave by its last fresh slot d(b,m). Trucks are
hired per slot, so a slot is a pool of capacity and a batch may split across slots. Under those two
facts the slot assignment is feasible exactly when, for every open slot t,

    sum of kg of chosen (b,m) with d(b,m) <= t  <=  truck capacity of the open slots up to t,

and earliest-deadline-first then finds it (`_schedule`). Writing the slot choice this way instead of as
x[b,m,s] removes the slot symmetry that made the direct form time out on 60-batch days.

Constraints
  each batch ships to at most one market (exactly the locked one if the dispatcher locked it);
  kg sold in a cell <= kg shipped there;
  the cumulative truck capacity rows above.

Objective (maximise forecast net INR)
  sales revenue - freight - handling - purchase value of unsold kg - purchase value of batches left at
  the hub that expire inside the horizon. All unit values come from cost_model.

Lading-point plans on forecast values. Lading-robust plans on P10 shelf life and P90 travel time.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import highspy
import numpy as np

import cost_model
from errors import LadingError, State
from plan_assembly import Leg, assemble
from plan_model import Arm, Plan, SolverInfo
from scenarios.model import Batch, Market, Scenario, Slot
from world import World

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@cache
def config() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CONFIG_PATH.read_text())
    return data


@dataclass(frozen=True)
class Variant:
    arm: Arm
    basis: str
    discounts: bool = True
    hard_shelf: bool = True


VARIANTS = {
    "lading-point": Variant("lading-point", "point"),
    "lading-robust": Variant("lading-robust", "robust"),
    "ablation-no-discount": Variant("ablation-no-discount", "robust", discounts=False),
    "ablation-soft-shelf": Variant("ablation-soft-shelf", "robust", hard_shelf=False),
}


@dataclass
class _Model:
    cost: list[float] = field(default_factory=list)
    upper: list[float] = field(default_factory=list)
    lower: list[float] = field(default_factory=list)
    integer: list[bool] = field(default_factory=list)
    rows_lo: list[float] = field(default_factory=list)
    rows_hi: list[float] = field(default_factory=list)
    rows: list[tuple[list[int], list[float]]] = field(default_factory=list)

    def col(self, cost: float, upper: float, integer: bool, lower: float = 0.0) -> int:
        self.cost.append(cost)
        self.upper.append(upper)
        self.lower.append(lower)
        self.integer.append(integer)
        return len(self.cost) - 1

    def row(self, idx: list[int], val: list[float], lo: float, hi: float) -> None:
        if idx:
            self.rows.append((idx, val))
            self.rows_lo.append(lo)
            self.rows_hi.append(hi)


@dataclass(frozen=True)
class Arc:
    batch: Batch
    market: Market
    deadline: Slot
    locked_slot: Slot | None


def build_arcs(scenario: Scenario, world: World, hard_shelf: bool = True) -> list[Arc]:
    """Every batch-market pair the program may use, with the last slot the batch can leave by."""
    point = World(scenario, "point")
    vetoed = {(v.batch_id, v.market_id) for v in scenario.controls.vetoes}
    locks = {lk.batch_id: lk for lk in scenario.controls.locks}
    arcs = []
    for b in scenario.batches:
        lock = locks.get(b.id)
        if lock is not None:
            m, s = scenario.market(lock.market_id), scenario.slot(lock.slot_id)
            if not point.sells(b, m) or not point.fresh_on_sale(b, m, s):
                raise LadingError(
                    State.LOCK_INFEASIBLE,
                    f"Lock {b.id} to {m.name} at {s.label} can't hold: it would be on sale at "
                    f"{point.sale_h(m, s):.1f} h and must be by {b.shelf_life_h - scenario.policy.safety_margin_h:.1f} h.",
                    path="controls.locks",
                )
            arcs.append(Arc(b, m, s, s))
            continue
        for m in scenario.markets:
            if not world.sells(b, m) or (b.id, m.id) in vetoed:
                continue
            fresh = world.fresh_slots(b, m)
            if fresh:
                arcs.append(Arc(b, m, fresh[-1], None))
            elif not hard_shelf and world.open_slots:
                arcs.append(Arc(b, m, world.open_slots[-1], None))
    return arcs


def plan_lading(
    scenario: Scenario, arm: str = "lading-robust", time_limit_s: float | None = None, mip_rel_gap: float | None = None
) -> Plan:
    variant = VARIANTS[arm]
    cfg = dict(config())
    if mip_rel_gap is not None:
        cfg["mip_rel_gap"] = mip_rel_gap
    world = World(scenario, variant.basis)
    pol = scenario.policy
    commodity = {c.id: c for c in scenario.commodities}
    model = _Model()

    arcs = build_arcs(scenario, world, variant.hard_shelf)
    x: dict[tuple[str, str], int] = {}
    for arc in arcs:
        b, m = arc.batch, arc.market
        purchase = commodity[b.commodity_id].purchase_inr_per_kg
        hub_loss = cost_model.spoilage_inr_per_kg(purchase) if world.expires_in_horizon(b) else 0.0
        unit = cost_model.route_inr_per_kg(m.transport_inr_per_kg, m.handling_inr_per_kg)
        penalty = 0.0
        if not variant.hard_shelf and arc.locked_slot is None and not world.fresh_slots(b, m):
            late_h = world.sale_h(m, world.open_slots[0]) - (world.shelf_h(b) - pol.safety_margin_h)
            penalty = cfg["soft_shelf_penalty_inr_per_kg_h"] * late_h * b.kg
        coef = -b.kg * unit - b.kg * cost_model.spoilage_inr_per_kg(purchase) + b.kg * hub_loss - penalty
        locked = arc.locked_slot is not None
        x[(b.id, m.id)] = model.col(coef, 1.0, True, lower=1.0 if locked else 0.0)

    levels = pol.discount_levels if variant.discounts else [0.0]
    pick: dict[tuple[str, str, float], int] = {}
    sold: dict[tuple[str, str, float], int] = {}
    cells = sorted({(arc.market.id, arc.batch.commodity_id) for arc in arcs})
    for mid, cid in cells:
        offer = scenario.offer(mid, cid)
        assert offer is not None
        c = commodity[cid]
        for d in levels:
            cap = cost_model.demand_cap_kg(offer.demand_kg, c.elasticity, d)
            unit = cost_model.sale_inr_per_kg(offer.price_inr_per_kg, d) + cost_model.spoilage_inr_per_kg(
                c.purchase_inr_per_kg
            )
            pick[(mid, cid, d)] = model.col(0.0, 1.0, True)
            sold[(mid, cid, d)] = model.col(unit, cap, False)

    by_batch: dict[str, list[int]] = defaultdict(list)
    by_cell: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for arc in arcs:
        j = x[(arc.batch.id, arc.market.id)]
        by_batch[arc.batch.id].append(j)
        by_cell[(arc.market.id, arc.batch.commodity_id)].append((j, arc.batch.kg))
    for cols in by_batch.values():
        model.row(cols, [1.0] * len(cols), 0.0, 1.0)

    for mid, cid in cells:
        cols = [sold[(mid, cid, d)] for d in levels]
        shipped = by_cell[(mid, cid)]
        model.row(cols + [j for j, _ in shipped], [1.0] * len(cols) + [-kg for _, kg in shipped], -np.inf, 0.0)
        picks = [pick[(mid, cid, d)] for d in levels]
        model.row(picks, [1.0] * len(picks), 1.0, 1.0)
        offer = scenario.offer(mid, cid)
        assert offer is not None
        for d in levels:
            cap = cost_model.demand_cap_kg(offer.demand_kg, commodity[cid].elasticity, d)
            model.row([sold[(mid, cid, d)], pick[(mid, cid, d)]], [1.0, -cap], -np.inf, 0.0)

    capacity = _free_capacity(world, arcs)
    cumulative = 0.0
    for t in world.open_slots:
        cumulative += capacity[t.id]
        due = [arc for arc in arcs if arc.locked_slot is None and arc.deadline.index <= t.index]
        model.row([x[(a.batch.id, a.market.id)] for a in due], [a.batch.kg for a in due], -np.inf, cumulative)

    offset = -sum(
        b.kg * cost_model.spoilage_inr_per_kg(commodity[b.commodity_id].purchase_inr_per_kg)
        for b in scenario.batches
        if world.expires_in_horizon(b)
    )
    limit = time_limit_s if time_limit_s is not None else cfg["live_time_limit_s"]
    values, info = _solve(model, offset, limit, cfg)

    chosen = [arc for arc in arcs if values[x[(arc.batch.id, arc.market.id)]] > 0.5]
    legs = _schedule(world, chosen, capacity)
    discounts = {(mid, cid): d for (mid, cid, d), j in pick.items() if values[j] > 0.5}
    return assemble(
        scenario,
        variant.arm,
        "robust" if variant.basis == "robust" else "point",
        legs,
        discounts,
        solver=info,
        locked={lk.batch_id for lk in scenario.controls.locks},
    )


def _free_capacity(world: World, arcs: list[Arc]) -> dict[str, float]:
    """Truck capacity per open slot after the dispatcher's locks have taken their room."""
    capacity = {s.id: world.slot_capacity_kg(s) for s in world.open_slots}
    for arc in arcs:
        if arc.locked_slot is not None and arc.locked_slot.id in capacity:
            capacity[arc.locked_slot.id] -= arc.batch.kg
            if capacity[arc.locked_slot.id] < -1e-9:
                raise LadingError(
                    State.LOCK_INFEASIBLE,
                    f"Locks at {arc.locked_slot.label} need more truck room than the slot has.",
                    path="controls.locks",
                )
    return capacity


def _schedule(world: World, chosen: list[Arc], capacity: dict[str, float]) -> list[Leg]:
    """Earliest deadline first: each batch fills the earliest slots with room, up to its deadline."""
    room = dict(capacity)
    legs = [Leg(a.batch.id, a.market.id, a.locked_slot.id, a.batch.kg) for a in chosen if a.locked_slot is not None]
    queue = sorted(
        (a for a in chosen if a.locked_slot is None),
        key=lambda a: (a.deadline.index, world.shelf_h(a.batch), a.batch.id),
    )
    for arc in queue:
        left = arc.batch.kg
        for s in world.open_slots:
            if s.index > arc.deadline.index or left <= 1e-9:
                break
            take = min(left, max(room[s.id], 0.0))
            if take > 1e-6:
                legs.append(Leg(arc.batch.id, arc.market.id, s.id, take))
                room[s.id] -= take
                left -= take
        if left > 1e-3:
            raise RuntimeError(f"EDF could not place {left:.1f} kg of {arc.batch.id}; capacity rows are wrong")
    return legs


def _solve(model: _Model, offset: float, time_limit_s: float, cfg: dict[str, Any]) -> tuple[np.ndarray, SolverInfo]:
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(time_limit_s))
    h.setOptionValue("mip_rel_gap", float(cfg["mip_rel_gap"]))
    h.setOptionValue("threads", int(cfg["threads"]))
    h.setOptionValue("random_seed", int(cfg["random_seed"]))

    n = len(model.cost)
    h.addVars(n, np.array(model.lower), np.array(model.upper))
    h.changeColsCost(n, np.arange(n, dtype=np.int32), np.array(model.cost))
    integer = [i for i, flag in enumerate(model.integer) if flag]
    if integer:
        h.changeColsIntegrality(
            len(integer), np.array(integer, dtype=np.int32), np.array([highspy.HighsVarType.kInteger] * len(integer))
        )
    starts, index, value = [], [], []
    for idx, val in model.rows:
        starts.append(len(index))
        index.extend(idx)
        value.extend(val)
    h.addRows(
        len(model.rows),
        np.array(model.rows_lo),
        np.array(model.rows_hi),
        len(index),
        np.array(starts, dtype=np.int32),
        np.array(index, dtype=np.int32),
        np.array(value, dtype=np.float64),
    )
    h.changeObjectiveSense(highspy.ObjSense.kMaximize)
    h.changeObjectiveOffset(offset)

    started = time.perf_counter()
    h.run()
    elapsed = time.perf_counter() - started
    status = h.getModelStatus()
    info = h.getInfo()
    has_solution = info.primal_solution_status == 2

    if status == highspy.HighsModelStatus.kOptimal:
        label = "OPTIMAL"
    elif status == highspy.HighsModelStatus.kTimeLimit and has_solution:
        label = "TIME_LIMIT"
    elif status == highspy.HighsModelStatus.kTimeLimit:
        raise LadingError(State.SOLVER_TIMEOUT, f"No feasible plan found within {time_limit_s:g} s.")
    elif status == highspy.HighsModelStatus.kInfeasible:
        raise LadingError(State.LOCK_INFEASIBLE, "The dispatcher locks can't all hold at once.")
    else:
        raise LadingError(State.SOLVER_UNAVAILABLE, f"Solver stopped with status {h.modelStatusToString(status)}.")

    values = np.array(h.getSolution().col_value)
    return values, SolverInfo(
        status=label,
        objective_inr=round(float(info.objective_function_value), 2),
        bound_inr=round(float(info.mip_dual_bound), 2),
        gap=round(float(info.mip_gap), 6),
        solve_s=round(elapsed, 3),
        n_vars=n,
        n_rows=len(model.rows),
        highs_version=h.version(),
    )
