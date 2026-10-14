# Security

## Trust story

The claim Lading makes is "this plan is feasible and beats FEFO on days it never saw". Each part of that has a check that doesn't trust the part before it:

- **Feasibility** is graded by `validate/`, which imports nothing from the planner, baselines, simulator, cost model or scenario models. It recomputes stock, slot validity, market offers, one price per cell, shelf life with the safety margin, order deadlines, truck capacity and every forecast total from the raw JSON. Tamper tests edit one value at a time and each must fail. The API refuses to return a Lading plan the validator rejects.
- **Advantage** is measured by executing plans in one simulator against realized draws from a separate seed stream, on held-out seeds generated after the planner config was frozen. The freeze is a hash in `results/freeze.json`; `make reproduce` refuses to run the held-out set if the config changed.
- **Information parity**: execution shocks live in a scenario block only the simulator reads. `planner/test_planner.py` proves the planner's output is unchanged when those shocks change.

## Input validation

- Every request body is a typed Pydantic model with `extra="forbid"`. Scenarios are checked against `schemas/scenario.json` (generated from the same models) and then for referential integrity. Errors are SCHEMA_INVALID with the exact field path.
- Size caps: 80 batches, 10 markets, 12 slots, 10 trucks, 50 simulation draws per request.
- Solves are rate limited per client IP (20 a minute, burst 6). `X-Forwarded-For` is only trusted when the connection comes from the configured proxy network. At most two solves run at once per worker; extra requests get SOLVER_UNAVAILABLE instead of queueing forever.
- `/results/{name}` serves only a fixed list of file names from a read-only directory baked into the image.
- Unexpected errors are logged server-side and returned as `INTERNAL_ERROR` with no stack trace.

## Runtime

- The API container runs as a non-root user, with a read-only root filesystem, `no-new-privileges`, a 1 GB memory cap and a 3 CPU cap.
- CORS allows only the origins in `ALLOWED_ORIGINS` (the Vercel production URL and `http://localhost:5173`), never `*`, and only GET and POST.
- TLS is terminated by Caddy with automatic certificates. The console can't call plain HTTP.

## Secrets

There are none. The API needs no keys, the console holds no tokens, and judge reproduction (`make setup && make test && make reproduce`) depends on no account. Deployment settings (SSH target, hostnames) live in an untracked `deploy/.env.deploy`; `.env*` files are gitignored.

## Reporting

Open an issue on the repository with "security" in the title, or contact the maintainer listed on the GitHub profile. Please don't include exploit details in a public issue.
