# Decisions

Each entry resolves an ambiguity in the PRD or records a deviation from it, with the reason.

## D1. Trucks are capacity per slot, not routed vehicles (2026-10-14)

PRD section 6 specifies "2-4 trucks, capacity in kg, available per slot", and the build prompt lists "truck capacity per slot" as the constraint. The first planner build modelled each truck as a vehicle serving one market per trip with a round-trip turnaround. On generated 40-batch days that form left an 11-16% optimality gap after 15 s (seed 0: incumbent 1.254M INR, bound 1.397M INR), so it couldn't meet the 10 s budget or produce deterministic results. The shipped model follows the PRD: each slot has the hired fleet's capacity, a batch may split across trucks and across slots, and routing a truck between markets inside a slot is out of scope. Every arm, the simulator and the validator use the same model.

## D2. Slot choice through deadlines (2026-10-14)

The MILP picks batch -> market (x[b,m]) and the price per commodity per market. Slots enter through each batch-market's last fresh slot and one cumulative capacity row per slot. With pooled per-slot capacity and splittable batches this is exactly the feasibility condition for an earliest-deadline-first schedule, which `_schedule` then builds. It removes the slot symmetry of the x[b,m,s] form: the same 60-batch days dropped from 400-1,800 binaries to 250-480 and solve to 0.5% in 1.7 s on average (max 14 s, tuning seeds 0-19). A brute-force enumeration on 5 tiny scenarios matches the MILP optimum exactly.

## D3. One price per commodity per market (2026-10-14)

The PRD lists discount as a decision dimension. A mandi doesn't sell the same tomatoes at two prices on the same day, so the discount is chosen per (market, commodity) and every batch in that cell carries it. The demand uplift applies to the cell. Every arm uses this rule.

## D4. Unsold consignment counts as spoiled (2026-10-14)

Stock delivered to a market but not sold within its demand is booked as spoiled at purchase value, because the hub doesn't haul it back. Spoiled kg = expired in transit + expired at the hub inside the horizon + delivered but unsold, reported separately in every results file.

## D5. MILP gap 0.5% and deterministic termination (2026-10-14)

`mip_rel_gap` is 0.005 and HiGHS runs single-threaded with a fixed seed, so evaluation solves end on the gap, not on the clock, and replays are byte-identical. The live API keeps the 10 s budget and labels any plan that hits it as SOLVER_TIMEOUT with its gap.

## D6. Replans are anchored on the previous plan (2026-10-15)

A replan freezes stock that already left as `controls.dispatched` and re-solves the open slots. A cold re-solve at a 0.5% gap reshuffled batches the disruption never touched (a no-op disruption on held-out seed 1007 changed 3 batches), which would make the diff lie about cause and effect. The replan pays a stability bonus of INR 5/kg for keeping a batch's market and INR 5,000 for keeping a cell's price (INR 2/kg still let a no-op at slot 0 move 2 batches on seed 1007) (`planner/config.json`), so the plan moves only what is worth more than that to move. The bonus is removed from the reported objective. A no-op disruption now changes nothing (test_replan.py).

## D7. Headline arm picked by a tuning-set rule (2026-10-15)

The PRD pre-registered Lading-robust (P10 shelf life, P90 travel) as the headline arm. Before the freeze, `results/tuning.json` recorded a rule: the headline is whichever Lading arm has the higher median paired net INR gain vs FEFO on tuning seeds 0-19. Lading-point won (+INR 76,247 vs +INR 35,423), so `planner/config.json` names it and the freeze hash covers that choice. Lading-robust is still planned, validated and reported on every held-out, stress and tuning day. Ablations A1 and A2 take the headline arm's basis so they ablate the arm being claimed.

## D8. Sharing the VPS's existing Caddy (2026-10-15)

The VPS already runs another project's Caddy on ports 80 and 443, so the bundled Caddy can't bind them and can't pass an ACME challenge on other ports. `deploy/deploy-api.sh` has a `shared` mode: the API joins that proxy's Docker network as `lading-api`, and one marked site block for the API hostname is appended to that proxy's Caddyfile, checked with `caddy validate` (the original is restored on failure) and applied with a zero-downtime `caddy reload`. The other project's site block and certificate are untouched (verified: its health endpoint answered 200 after the reload). The `standalone` profile with Lading's own Caddy remains the default for a clean host.

## D9. Results identity excludes wall-clock time (2026-10-15)

Solve times can't be byte-identical across runs, so they live only in `results/timings.json`, which the replay and clean-room checks skip. The manifest's `commit` is the last commit touching code or data the results depend on (`EVAL_PATHS` in the harness), so later docs or deploy commits don't invalidate a clean-room diff.
