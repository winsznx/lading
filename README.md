# Lading

Plans which produce goes where, when, and at what price, so less of it rots.

Lading is a dispatch planner for a produce aggregation hub. Each morning it decides, for every batch on the floor, which market it goes to, which truck slot it leaves on, and what discount it sells at, with "on sale before it expires" as a hard rule. One mixed-integer program on HiGHS plans all batches jointly. A dispatcher can lock or veto any assignment and the plan re-solves around it.

**Measured, not targeted.** On 50 held-out synthetic days the planner never saw, executed against realized demand, travel delays and shelf life (30 realized days each), Lading vs first-expiry-first-out (FEFO):

| | Median paired change | IQR | Days Lading wins |
|---|---|---|---|
| Net revenue | **+₹58,942** per day | +₹41,124 to +₹88,320 | 50 of 50 |
| Spoiled stock | **−654 kg** per day | −1,154 to −289 kg | 40 of 50 |
| Demand filled | **+2.24 pp** | +1.14 to +3.28 pp | 47 of 50 |

0 constraint violations across all 50 Lading plans, from a validator that imports none of the planner's code. Source: [`results/heldout.json`](results/heldout.json), [`results/verdict.json`](results/verdict.json), produced by `make reproduce`. All data is synthetic (see [How could this be misleading](#how-could-this-be-misleading)).

- Console: **CONSOLE_URL**
- API: https://vps-api-host.invalid ([/docs](https://vps-api-host.invalid/docs))

GIFS_HERE

## Try it (about 2 minutes)

1. Open the console. Held-out day seed 1007 is preloaded (58 batches, 6 mandis around Kolar, 4 trucks).
2. Press **R** (Run plan). The live solve takes about 3-4 s. The board fills: slots across, markets down, one card per batch with arrival time against expiry. The right strip shows Lading vs FEFO executed over 30 realized days, and the row under it says whether the independent validator found any violation.
3. Click any card. The drawer shows why the batch went where it did and why each other market lost, for example "Chennai, not Hyderabad: Hyderabad arrival 13h vs 12h shelf life left." Press **Veto** on its market and the plan re-solves around your decision in about 4 s.
4. Press **1** (a +8 h delay on every trip to Chennai). The replan runs live in about 4-5 s, moved cards slide to their new cell, and the line under the board reads cause → effect.
5. Press **E** for the Evidence tab: the 50-day held-out table, ablations, stress families, the elasticity sweep, controls, assumptions and the manifest, all read from `results/`.
6. The scenario picker also has **P4: the best price is too far**, a hand-built day where Delhi pays the most but is 22 h away. FIFO ships short-life stock there and loses it; Lading says why it won't.

## Reproduce

```bash
git clone <this repo> && cd lading
make setup        # uv sync --frozen (Python 3.11, pinned HiGHS 1.11.0) + npm ci
make test         # 100+ tests
make reproduce    # ~10 min on 8 cores: tuning → freeze check → held-out → stress → ablations → sweep → controls
```

`make reproduce` regenerates every file in `results/`. Apart from `timings.json` (wall-clock solve times), a second run is byte-identical; `make clean-room` clones the repo into a temp dir, reruns everything and diffs. Setup, deploy and organizer-data notes are in [docs/SETUP.md](docs/SETUP.md).

## How could this be misleading

Read this before the table above.

- **We wrote the generator, so we wrote the test.** Every scenario is synthetic, from a seeded generator whose assumptions are all in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). Mitigations: the planner config was frozen and hashed before the held-out seeds were generated ([docs/GATES.md](docs/GATES.md)); plans are executed on a separate random stream; no organizer dataset was published, but `data/organizer/` is wired in as a separate held-out group if one appears. A generator we didn't write could give a different answer.
- **The in-model win would prove nothing.** FEFO's plan is a feasible point of Lading's MILP, so on the planner's own forecast Lading wins by construction. None of the numbers above are in-model: every arm is planned on the forecast and executed in one simulator against the same realized draws.
- **A weak baseline would flatter us.** FEFO here is the careful human rule, not FIFO: shortest shelf life first, the best net margin among markets it can reach fresh, the same safety margin, truck capacity, costs and forecast Lading gets, a comparison against holding the stock, and a markdown when stock would otherwise go unsold ([baselines/fefo.py](baselines/fefo.py)). FIFO is reported too, and fails the validator on 43 of 50 days.
- **Spoilage can be "won" by shipping nothing.** That's why demand filled and net ₹ sit next to spoiled kg everywhere. Lading fills more demand than FEFO (+2.24 pp median, 47 of 50 days), so its lower spoilage doesn't come from holding stock back.
- **The headline arm changed after pre-registration.** The PRD pre-registered Lading-robust (planning on P10 shelf life and P90 travel). On the 20 tuning days it gained ₹35,423 median vs ₹76,247 for Lading-point, so a rule written before the freeze made Lading-point the headline. On held-out, Lading-robust also beats FEFO (+₹60,791 median, 40 of 50 days; −448 kg, 32 of 50) but less consistently, and it is worse than FEFO on spoilage in two stress families. Both are in every table.
- **Discount value rests on an elasticity assumption.** Removing discounts (ablation A1) costs ₹24,511 a day at the median and adds 919 kg of spoilage. If real elasticity is 0.5x to 1.5x what we assumed, the median gain over FEFO stays between ₹55,151 and ₹69,067 ([results/sensitivity.json](results/sensitivity.json)).
- **The hard shelf-life constraint is cheap but not free of trade-offs.** Relaxing it to a penalty (ablation A2) changes median net by −₹118 and produces 25 shelf-life violations across 19 of 50 plans.
- **One control failed.** P2 (a healthy day with ample shelf life, trucks and demand) required both arms to spoil under 2% of stock. Both spoil up to 7.2%, all of it delivered-but-unsold stock when realized demand comes in under forecast, because unsold consignment at a mandi is booked as spoiled ([DECISIONS D4](docs/DECISIONS.md)). Net ₹ converges within 1.0%, which is the "no invented advantage" half of the control. The failure is kept in [results/controls.json](results/controls.json) and GATES.md.
- **The model is simpler than a real hub.** Trucks are capacity per slot, not routed vehicles (a routed version left a 16% optimality gap at 15 s, [DECISIONS D1](docs/DECISIONS.md)); demand isn't split by hour within the 48 h window; prices are fixed per market. Both arms live with the same simplifications, but real gains could be smaller.
- **Some held-out seeds were seen during development.** Seeds 1003, 1007, 1011 and 1020 were planned while building the replan and API layers. No planner setting was changed after seeing them; the one value tuned on them only affects replans. Logged in GATES.md before the freeze.
- **Optimality gap.** Solves stop at a 0.5% relative gap so the evaluation is deterministic; the gap is in every row of the results.

## What's in the box

| Path | What it is |
|---|---|
| [`planner/`](planner/) | The MILP, decision objects, disruption replans, brute-force reference test |
| [`baselines/`](baselines/) | FEFO-greedy (the bar) and FIFO (the floor) |
| [`validate/`](validate/) | Independent validator. Imports nothing from the repo; a test enforces it |
| [`sim/`](sim/) | Execution simulator and realized draws on a separate seed stream |
| [`cost_model.py`](cost_model.py) | The only place money is computed |
| [`evaluation/`](evaluation/) | `make reproduce`: split, freeze check, campaigns, falsifier |
| [`explain/`](explain/) | Reasons and cause → effect lines from decision objects, no LLM |
| [`api/`](api/), [`web/`](web/) | FastAPI service on the VPS, React console on Vercel |
| [`results/`](results/) | Every number quoted anywhere |
| [`docs/`](docs/) | [ARCHITECTURE](docs/ARCHITECTURE.md), [ASSUMPTIONS](docs/ASSUMPTIONS.md), [DECISIONS](docs/DECISIONS.md), [GATES](docs/GATES.md), [SETUP](docs/SETUP.md) |

The rules this build was held to are in [BUILD_CONTRACT.md](BUILD_CONTRACT.md); the security posture is in [SECURITY.md](SECURITY.md).
