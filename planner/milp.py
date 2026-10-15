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
from typing import Any, Literal

import highspy
import numpy as np

import cost_model
from errors import LadingError, State
from plan_assembly import Leg, assemble
from plan_model import Arm, Plan, SolverInfo
from scenarios.model import Batch, Market, Scenario, Slot
from world import World, check_locks

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


LADING_ARMS = ("lading-point", "lading-robust")
ABLATIONS = ("ablation-no-discount", "ablation-soft-shelf")


def variant(arm: str) -> Variant:
    """The two Lading arms, and the ablations A1 (no discount) and A2 (soft shelf life), which take the
    frozen headline arm's planning basis so they ablate exactly the arm that is claimed."""
    if arm == "lading-point":
        return Variant("lading-point", "point")
    if arm == "lading-robust":
        return Variant("lading-robust", "robust")
    basis = variant(str(config()["headline_arm"])).basis
    if arm == "ablation-no-discount":
        return Variant("ablation-no-discount", basis, discounts=False)
    if arm == "ablation-soft-shelf":
        return Variant("ablation-soft-shelf", basis, hard_shelf=False)
    raise ValueError(f"unknown Lading arm '{arm}'")


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
    kg: float


def build_arcs(scenario: Scenario, world: World, hard_shelf: bool = True) -> list[Arc]:
    """Every batch-market pair the program may use, with the last slot the batch can leave by."""
    check_locks(scenario)
    vetoed = {(v.batch_id, v.market_id) for v in scenario.controls.vetoes}
    locks = {lk.batch_id: lk for lk in scenario.controls.locks}
    arcs = []
    for b in scenario.batches:
        kg = world.on_hand_kg(b)
        if kg <= 1e-9:
            continue
        committed = world.committed_market(b)
        lock = locks.get(b.id)
        if lock is not None:
            m, s = scenario.market(lock.market_id), scenario.slot(lock.slot_id)
            arcs.append(Arc(b, m, s, s, kg))
            continue
        for m in scenario.markets:
            if not world.sells(b, m) or (b.id, m.id) in vetoed or (committed and m.id != committed):
                continue
            fresh = world.fresh_slots(b, m)
            if fresh:
                arcs.append(Arc(b, m, fresh[-1], None, kg))
            elif not hard_shelf and world.open_slots:
                arcs.append(Arc(b, m, world.open_slots[-1], None, kg))
    return arcs


def in_transit(scenario: Scenario) -> tuple[dict[tuple[str, str], float], float]:
    """Stock already on the road: kg arriving saleable per (market, commodity) on the forecast, and the
    fixed INR it contributes before sales. Sold kg carry +purchase in the objective (unsold = shipped -
    sold is what costs purchase value), so every kg on the road is debited its purchase value here,
    exactly as a shipping arc is."""
    point = World(scenario, "point")
    arriving: dict[tuple[str, str], float] = defaultdict(float)
    fixed = 0.0
    for leg in scenario.controls.dispatched:
        b, m, s = scenario.batch(leg.batch_id), scenario.market(leg.market_id), scenario.slot(leg.slot_id)
        purchase = scenario.commodity(b.commodity_id).purchase_inr_per_kg
        fixed -= leg.kg * cost_model.route_inr_per_kg(m.transport_inr_per_kg, m.handling_inr_per_kg)
        fixed -= leg.kg * cost_model.spoilage_inr_per_kg(purchase)
        if point.arrives_before_expiry(b, m, s):
            arriving[(m.id, b.commodity_id)] += leg.kg
    return arriving, fixed


def plan_lading(
    scenario: Scenario,
    arm: str = "lading-robust",
    time_limit_s: float | None = None,
    mip_rel_gap: float | None = None,
    previous: Plan | None = None,
) -> Plan:
    """Solve one arm. With `previous` (a replan), keeping a batch's market or a cell's price earns a small
    stability bonus, so the new plan only moves what the disruption forces it to move."""
    spec = variant(arm)
    cfg = dict(config())
    if mip_rel_gap is not None:
        cfg["mip_rel_gap"] = mip_rel_gap
    world = World(scenario, spec.basis)
    pol = scenario.policy
    commodity = {c.id: c for c in scenario.commodities}
    model = _Model()

    arcs = build_arcs(scenario, world, spec.hard_shelf)
    arriving, fixed_inr = in_transit(scenario)
    kept_market = {sh.batch_id: sh.market_id for sh in previous.shipments} if previous else {}
    kept_price = {(p.market_id, p.commodity_id): p.discount for p in previous.prices} if previous else {}
    stick_kg = cfg["replan_stability_inr_per_kg"] if previous else 0.0
    stick_cell = cfg["replan_stability_inr_per_price"] if previous else 0.0
    bonus: dict[int, float] = {}
    x: dict[tuple[str, str], int] = {}
    for arc in arcs:
        b, m, kg = arc.batch, arc.market, arc.kg
        purchase = commodity[b.commodity_id].purchase_inr_per_kg
        hub_loss = cost_model.spoilage_inr_per_kg(purchase) if world.expires_in_horizon(b) else 0.0
        unit = cost_model.route_inr_per_kg(m.transport_inr_per_kg, m.handling_inr_per_kg)
        penalty = 0.0
        if not spec.hard_shelf and arc.locked_slot is None and not world.fresh_slots(b, m):
            late_h = world.sale_h(m, world.open_slots[0]) - (world.shelf_h(b) - pol.safety_margin_h)
            penalty = cfg["soft_shelf_penalty_inr_per_kg_h"] * late_h * kg
        coef = -kg * unit - kg * cost_model.spoilage_inr_per_kg(purchase) + kg * hub_loss - penalty
        locked = arc.locked_slot is not None
        stick = stick_kg * kg if kept_market.get(b.id) == m.id else 0.0
        x[(b.id, m.id)] = model.col(coef + stick, 1.0, True, lower=1.0 if locked else 0.0)
        bonus[x[(b.id, m.id)]] = stick

    ladder = pol.discount_levels if spec.discounts else [0.0]

    def levels_at(market_id: str) -> list[float]:
        """A fixed order (a destination with a deadline) is bought at its agreed price, never marked down."""
        return [0.0] if scenario.market(market_id).deliver_by_h is not None else ladder

    pick: dict[tuple[str, str, float], int] = {}
    sold: dict[tuple[str, str, float], int] = {}
    cells = sorted({(arc.market.id, arc.batch.commodity_id) for arc in arcs} | set(arriving))
    for mid, cid in cells:
        offer = scenario.offer(mid, cid)
        assert offer is not None
        c = commodity[cid]
        for d in levels_at(mid):
            cap = cost_model.demand_cap_kg(offer.demand_kg, c.elasticity, d)
            unit = cost_model.sale_inr_per_kg(offer.price_inr_per_kg, d) + cost_model.spoilage_inr_per_kg(
                c.purchase_inr_per_kg
            )
            stick = stick_cell if kept_price.get((mid, cid)) == d else 0.0
            pick[(mid, cid, d)] = model.col(stick, 1.0, True)
            bonus[pick[(mid, cid, d)]] = stick
            sold[(mid, cid, d)] = model.col(unit, cap, False)

    by_batch: dict[str, list[int]] = defaultdict(list)
    by_cell: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for arc in arcs:
        j = x[(arc.batch.id, arc.market.id)]
        by_batch[arc.batch.id].append(j)
        by_cell[(arc.market.id, arc.batch.commodity_id)].append((j, arc.kg))
    for cols in by_batch.values():
        model.row(cols, [1.0] * len(cols), 0.0, 1.0)

    for mid, cid in cells:
        levels = levels_at(mid)
        cols = [sold[(mid, cid, d)] for d in levels]
        shipped = by_cell[(mid, cid)]
        model.row(
            cols + [j for j, _ in shipped],
            [1.0] * len(cols) + [-kg for _, kg in shipped],
            -np.inf,
            arriving.get((mid, cid), 0.0),
        )
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
        model.row([x[(a.batch.id, a.market.id)] for a in due], [a.kg for a in due], -np.inf, cumulative)

    offset = fixed_inr - sum(
        world.on_hand_kg(b) * cost_model.spoilage_inr_per_kg(commodity[b.commodity_id].purchase_inr_per_kg)
        for b in scenario.batches
        if world.expires_in_horizon(b)
    )
    limit = time_limit_s if time_limit_s is not None else cfg["live_time_limit_s"]
    values, info = _solve(model, offset, limit, cfg)
    paid = sum(v for j, v in bonus.items() if v and values[j] > 0.5)
    if paid:
        info = info.model_copy(
            update={
                "objective_inr": round(info.objective_inr - paid, 2),
                "bound_inr": round(info.bound_inr - paid, 2),
            }
        )

    chosen = [arc for arc in arcs if values[x[(arc.batch.id, arc.market.id)]] > 0.5]
    legs = _schedule(world, chosen, capacity)
    fixed = [Leg(d.batch_id, d.market_id, d.slot_id, d.kg) for d in scenario.controls.dispatched]
    discounts = {(mid, cid): d for (mid, cid, d), j in pick.items() if values[j] > 0.5}
    return assemble(
        scenario,
        spec.arm,
        "robust" if spec.basis == "robust" else "point",
        fixed + legs,
        discounts,
        solver=info,
        locked=locked_legs(scenario, legs),
    )


def locked_legs(scenario: Scenario, legs: list[Leg]) -> set[tuple[str, str, str]]:
    """Legs the planner may not move: stock already on the road and the dispatcher's locks."""
    out = {(d.batch_id, d.market_id, d.slot_id) for d in scenario.controls.dispatched}
    lock_of = {(lk.batch_id, lk.market_id, lk.slot_id) for lk in scenario.controls.locks}
    return out | {
        (leg.batch_id, leg.market_id, leg.slot_id)
        for leg in legs
        if (leg.batch_id, leg.market_id, leg.slot_id) in lock_of
    }


def _free_capacity(world: World, arcs: list[Arc]) -> dict[str, float]:
    """Truck capacity per open slot after the dispatcher's locks have taken their room."""
    capacity = {s.id: world.slot_capacity_kg(s) for s in world.open_slots}
    for arc in arcs:
        if arc.locked_slot is not None and arc.locked_slot.id in capacity:
            capacity[arc.locked_slot.id] -= arc.kg
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
    legs = [Leg(a.batch.id, a.market.id, a.locked_slot.id, a.kg) for a in chosen if a.locked_slot is not None]
    queue = sorted(
        (a for a in chosen if a.locked_slot is None),
        key=lambda a: (a.deadline.index, world.shelf_h(a.batch), a.batch.id),
    )
    for arc in queue:
        left = arc.kg
        for s in world.open_slots:
            if s.index > arc.deadline.index or left <= 1e-9:
                break
            take = min(left, max(room[s.id], 0.0))
            if take > 1e-6:
                legs.append(Leg(arc.batch.id, arc.market.id, s.id, take))
                room[s.id] -= take
                left -= take
        if left > 1e-3:
            raise RuntimeError(
                f"EDF could not place {left:.1f} kg of {arc.batch.id}; capacity rows are wrong"
            )
    return legs


def _solve(
    model: _Model, offset: float, time_limit_s: float, cfg: dict[str, Any]
) -> tuple[np.ndarray, SolverInfo]:
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
            len(integer),
            np.array(integer, dtype=np.int32),
            np.array([highspy.HighsVarType.kInteger] * len(integer)),
        )
    starts: list[int] = []
    index: list[int] = []
    value: list[float] = []
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

    label: Literal["OPTIMAL", "TIME_LIMIT"]
    if status == highspy.HighsModelStatus.kOptimal:
        label = "OPTIMAL"
    elif status == highspy.HighsModelStatus.kTimeLimit and has_solution:
        label = "TIME_LIMIT"
    elif status == highspy.HighsModelStatus.kTimeLimit:
        raise LadingError(State.SOLVER_TIMEOUT, f"No feasible plan found within {time_limit_s:g} s.")
    elif status == highspy.HighsModelStatus.kInfeasible:
        raise LadingError(State.LOCK_INFEASIBLE, "The dispatcher locks can't all hold at once.")
    else:
        raise LadingError(
            State.SOLVER_UNAVAILABLE, f"Solver stopped with status {h.modelStatusToString(status)}."
        )

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
