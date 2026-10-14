# Setup

## Run it locally

Needs [uv](https://docs.astral.sh/uv/) 0.8+ (it installs Python 3.11 itself) and Node 22+.

```bash
make setup        # uv sync --frozen, npm ci in web/
make test         # pytest: 100+ tests, ~10 s
make reproduce    # the full evaluation, ~6 min on 8 cores; writes results/*.json
make serve        # API on http://127.0.0.1:8000 (docs at /docs)
make web-dev      # console on http://localhost:5173, talking to the local API
```

`make reproduce` uses every core but one. Set `LADING_WORKERS=1` to run it serially. `results/timings.json` is the only output that changes between runs; `make clean-room` clones the repo into a temp dir, reruns everything and diffs the rest byte for byte.

## Evaluate one scenario by hand

```bash
uv run python -m scenarios.scenario_gen --seed 1007 --out /tmp/day.json
uv run python -c "
import json; from scenarios.loader import load; from pathlib import Path
from planner.milp import plan_lading
s = load(Path('/tmp/day.json')); open('/tmp/plan.json','w').write(plan_lading(s, 'lading-point').model_dump_json())"
uv run python -m validate.validator /tmp/day.json /tmp/plan.json
```

## Organizer data

Drop scenario files into `data/organizer/`. Files already in the Lading schema (`schema_version: lading-scenario-v1`, `source: organizer`) load directly and `make reproduce` adds them as a separate held-out group. Any other structure needs a converter registered in `scenarios/organizer.py`; until then the loader fails with SCHEMA_INVALID instead of guessing.

## Deploy

Backend (API + Caddy) to a VPS over SSH, frontend to Vercel with the CLI. Put the settings in an untracked `deploy/.env.deploy`:

```bash
LADING_SSH=user@host
LADING_SSH_KEY=$HOME/.ssh/your_key
API_DOMAIN=lading-api.<ip-with-dashes>.sslip.io     # or your own domain pointing at the host
ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app,http://localhost:5173
VITE_API_URL=https://lading-api.<ip-with-dashes>.sslip.io
EDGE_MODE=standalone                                # or shared, see below
```

```bash
make deploy-api   # rsync the bundle, docker compose up -d --build, wait for /health over HTTPS
make deploy-web   # npm ci, build with VITE_API_URL, vercel deploy --prod
make smoke        # LADING_API_URL=... LADING_WEB_URL=... : health, scenarios, one plan, page → API, CORS
```

Both scripts are safe to re-run.

**Standalone host** (ports 80 and 443 free): `EDGE_MODE=standalone` starts the bundled Caddy, which gets a certificate for `API_DOMAIN`. Without a domain, `<ip-with-dashes>.sslip.io` resolves to the host and still gets a real certificate, which the console needs because a Vercel page can't call plain HTTP.

**Host that already runs a Caddy** (the current deployment shares a VPS with another project): set `EDGE_MODE=shared`, `EDGE_NETWORK` (that proxy's Docker network), `EDGE_CADDY` (its container) and `EDGE_CADDYFILE` (its Caddyfile on the host). The API joins that network as `lading-api`, and the script appends one marked site block for `API_DOMAIN`, validates the config with `caddy validate`, restores the backup if validation fails, and reloads with zero downtime. If that other project redeploys and overwrites its Caddyfile, re-run `make deploy-api` to add the block back.
