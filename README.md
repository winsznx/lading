# Lading

Plans which produce goes where, when, and at what price, so less of it rots.

Lading is a dispatch planner for a produce aggregation hub. Each morning it decides, for every batch on the floor, which market it goes to, which truck slot it leaves on, and what discount it sells at, with "on sale before it expires" as a hard rule. One mixed-integer program on HiGHS plans all batches jointly. A dispatcher can lock or veto any assignment and the plan re-solves around it.

**Measured, not targeted.** On 50 held-out synthetic days the planner never saw, executed against realized demand, travel delays and shelf life (30 realized days each), Lading vs first-expiry-first-out (FEFO):

| | Median paired change | IQR | Days Lading wins |
|---|---|---|---|
| Net revenue | **+₹48,588** per day | +₹30,258 to +₹80,447 | 50 of 50 |
| Spoiled stock | **−366 kg** per day | −859 kg to −27 kg | 39 of 50 |
| Demand filled | **+1.64 pp** | +0.91 to +2.67 pp | 44 of 50 |

0 constraint violations across all 50 Lading plans, from a validator that imports none of the planner's code. Source: [`results/heldout.json`](results/heldout.json), [`results/verdict.json`](results/verdict.json), produced by `make reproduce`. All data is synthetic (see [How could this be misleading](#how-could-this-be-misleading)).

Read four things with that table. The headline arm is Lading-point, picked by a rule written before the freeze; the PRD had pre-registered Lading-robust. The FEFO baseline was strengthened after a cold audit, and these numbers come from the rerun against the stronger version. The P2 healthy-day control failed. Solver runs on the build Mac and the deploy VPS drift: the Mac gave +₹46,412, and the numbers here come from the VPS, where the console solves. Each is detailed under [How could this be misleading](#how-could-this-be-misleading).

- Console: **https://lading-seven.vercel.app**
- API, through the same origin: https://lading-seven.vercel.app/api ([docs](https://lading-seven.vercel.app/api/docs), [health](https://lading-seven.vercel.app/api/health), [verdict](https://lading-seven.vercel.app/api/results/verdict.json))

![Plan run on held-out seed 1007: press R, the board fills, Lading vs FEFO outcome strip, a batch drawer with its reasons](docs/media/plan-run.gif)

*Real session, real time: the deployed console solving held-out day 1007 live (about 4 s), then a batch's reasons.*

![Disruption replan: a +8 h delay on every trip to Bengaluru, two leafy-green batches move, the cause → effect line updates](docs/media/disruption-replan.gif)

*Real session, real time: plan, then disruption 1 (Bengaluru +8 h). The replan runs live; moved cards are outlined and the changes panel gives each one's reason.*

## Try it (about 2 minutes)

1. Open the console. Held-out day seed 1007 is preloaded (58 batches, 6 mandis around Kolar, 4 trucks).
2. Press **R** (Run plan). The live solve takes about 3-4 s. The board fills: slots across, markets down, one card per batch with arrival time against expiry. The right strip shows Lading vs FEFO executed over 30 realized days, and the row under it says whether the independent validator found any violation.
3. Click any card. The drawer shows why the batch went where it did and why each other market lost, for example "Bengaluru, not Hyderabad: Hyderabad arrival 13h vs 12h shelf life left." Press **Veto** on its market and the plan re-solves around your decision in about 4 s.
4. Press **1** (a +8 h delay on every trip to Bengaluru). The replan runs live in about 4-5 s, moved cards slide to their new cell, and the line under the board reads cause → effect.
5. Press **E** for the Evidence tab: the 50-day held-out table, ablations, stress families, the elasticity sweep, controls, assumptions and the manifest, all read from `results/`.
6. The scenario picker also has **P4: the best price is too far**, a hand-built day where Delhi pays the most but is 22 h away. FIFO ships short-life stock there and loses it; Lading says why it won't.

## Reproduce

```bash
git clone <this repo> && cd lading
make setup        # uv sync --frozen (Python 3.11, pinned HiGHS 1.11.0) + npm ci
make test         # 100+ tests
make reproduce    # ~10 min on 8 cores: tuning → freeze check → held-out → stress → ablations → sweep → controls
```

`make reproduce` regenerates every file in `results/`. Apart from `timings.json` (wall-clock solve times), a second run on the same kind of machine is byte-identical. The committed results come from the deploy host (linux/amd64), the same machine the console solves on, via `deploy/reproduce-on-host.sh`; on another CPU, see the drift caveat below. Setup, deploy and organizer-data notes are in [docs/SETUP.md](docs/SETUP.md).

## How could this be misleading

Read this before the table above.

- **We wrote the generator, so we wrote the test.** Every scenario is synthetic, from a seeded generator whose assumptions are all in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). Mitigations: the planner config was frozen and hashed before the held-out seeds were generated ([docs/GATES.md](docs/GATES.md)); plans are executed on a separate random stream; no organizer dataset was published, but `data/organizer/` is wired in as a separate held-out group if one appears. A generator we didn't write could give a different answer.
- **The in-model win would prove nothing.** FEFO's plan is a feasible point of Lading's MILP, so on the planner's own forecast Lading wins by construction. None of the numbers above are in-model: every arm is planned on the forecast and executed in one simulator against the same realized draws.
- **A weak baseline would flatter us.** FEFO here is the careful human rule, not FIFO: shortest shelf life first, the best net margin among markets it can reach fresh, the same safety margin, truck capacity, costs and forecast Lading gets, a comparison against holding the stock, and a markdown when stock would otherwise go unsold ([baselines/fefo.py](baselines/fefo.py)). FIFO is reported too, and fails the validator on 43 of 50 days.
- **Spoilage can be "won" by shipping nothing.** That's why demand filled and net ₹ sit next to spoiled kg everywhere. Lading fills more demand than FEFO (+1.64 pp median, 44 of 50 days), so its lower spoilage doesn't come from holding stock back. The spoilage gain is the weakest of the three: on 11 of 50 days Lading spoils more than FEFO.
- **The headline arm changed after pre-registration.** The PRD pre-registered Lading-robust (planning on P10 shelf life and P90 travel). On the 20 tuning days it gained ₹29,771 median vs ₹50,431 for Lading-point, so a rule written before the freeze made Lading-point the headline. On held-out, Lading-robust's median net gain is about the same (+₹48,678) but it wins on fewer days (38 of 50; −100 kg spoiled, 31 of 50), and it spoils more than FEFO in two stress families (truck loss, wide shelf-life uncertainty). Both are in every table.
- **Discount value rests on an elasticity assumption.** Removing discounts (ablation A1) costs ₹27,818 a day at the median and adds 955 kg of spoilage. If real elasticity is 0.5x to 1.5x what we assumed, the median gain over FEFO stays between ₹40,343 and ₹63,890 and Lading wins on at least 49 of 50 days at every point ([results/sensitivity.json](results/sensitivity.json)). The gain shrinks as elasticity rises, because FEFO's own markdowns get more valuable.
- **The hard shelf-life constraint is cheap but not free of trade-offs.** Relaxing it to a penalty (ablation A2) changes median net by −₹275 and produces 20 shelf-life violations across 15 of 50 plans.
- **One control failed.** P2 (a healthy day with ample shelf life, trucks and demand) required both arms to spoil under 2% of stock. Both spoil up to 6.8%, all of it delivered-but-unsold stock when realized demand comes in under forecast, because unsold consignment at a mandi is booked as spoiled ([DECISIONS D4](docs/DECISIONS.md)). Net ₹ converges within 1.3%, which is the "no invented advantage" half of the control. The failure is kept in [results/controls.json](results/controls.json) and GATES.md.
- **The model is simpler than a real hub.** Trucks are capacity per slot, not routed vehicles (a routed version left a 16% optimality gap at 15 s, [DECISIONS D1](docs/DECISIONS.md)), so one truck can carry loads for two markets in the same slot, each timed as a direct run, and "0 violations" means feasible under that model. Demand isn't split by hour within the 48 h window, and prices are fixed per market. Both arms live with the same simplifications, but real gains could be smaller.
- **The baseline was strengthened after a first held-out run.** A cold audit found FEFO could only mark down to 0% or 30% while Lading uses the whole ladder. FEFO now prices every step, the planner was re-frozen and the held-out set rerun. The first run's numbers (+₹58,942 median against the weaker FEFO) are in git history and GATES.md; everything quoted here is from the rerun.
- **Some held-out seeds were seen during development.** Seeds 1003, 1007, 1011 and 1020 were planned while building the replan and API layers. No planner setting was changed after seeing them; the one value tuned on them only affects replans. Logged in GATES.md before the freeze.
- **Optimality gap and CPU drift.** Solves stop at a 0.5% relative gap so the evaluation is deterministic on one machine; the gap is in every row of the results. A different CPU can stop at a different plan inside the same gap. Run on the build Mac (arm64), the same code gave a median net gain of +₹46,412 instead of +₹48,588, and the Lading-point plan matched on only 6 of 50 days (median per-day difference ₹1,590, largest ₹39,301). FEFO, being greedy, was identical. The committed numbers come from the deploy host so the live console matches them.
- **The live budget is tighter than the evaluation's.** The console gives the solver 10 s; evaluation allowed 60 s. On the deploy host, with four held-out solves running at once, the slowest took 20.6 s and the p90 was 13.8 s, so a live solve of some days could hit the budget. The console then says so and shows the gap. The curated days solve in about 4 s.

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
