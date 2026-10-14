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
