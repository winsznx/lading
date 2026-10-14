# Build contract

These rules bind every change to this repo. When a change can't meet one, the change doesn't land.

1. **The PRD is the source of truth.** Where the build had to resolve an ambiguity or deviate, the decision and its reason are recorded in [docs/DECISIONS.md](docs/DECISIONS.md).
2. **No fake numbers.** Every number on any surface (console, README, film, submission form) traces to a file in `results/` produced by `make reproduce`.
3. **Targets stay labelled as targets until measured.** A measured result replaces its target, including when it's worse.
4. **No silent fallback.** If the solver fails or times out, the product says so. It never shows a baseline plan labelled as Lading.
5. **Failures and withdrawn claims are kept.** They go in [docs/GATES.md](docs/GATES.md) with a date. Nothing is deleted to look better.
6. **Matched comparisons only.** Every arm uses the same scenario, forecast, cost model (`cost_model.py`), simulator (`sim/`) and validator (`validate/`).
