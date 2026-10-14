# Gates

Dated log of checkpoints, pre-registered splits, freezes, failures and withdrawn claims. Entries are appended, never edited away.

## Checkpoints

| When (WAT) | Product h | Proof h | Docs h | Hours left | Note |
|---|---|---|---|---|---|
| 2026-10-14 23:20 | 0.0 | 0.0 | 0.1 | 20.1 | Repo scaffolded, build contract written |

## Held-out exposure during development (2026-10-15 00:00 WAT)

Logged before the freeze so it can't be hidden later. While building the replan and API layers, held-out seeds 1003, 1007, 1011 and 1020 were planned to exercise disruptions, and seed 1007 was run end to end through the API once (Lading-point 5,850 kg spoiled, 94.3% filled, INR 17.45 lakh net vs FEFO 8,740 kg, 94.5%, INR 16.24 lakh, 30 draws). No planner objective, constraint, basis or gap setting was changed after seeing these. The one parameter tuned on them is the replan stability bonus (DECISIONS D6), which only affects replans, not any number in `results/heldout.json`.
