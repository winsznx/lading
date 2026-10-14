"""Smoke test against the live deployment, and live verification of every curated scenario.

    LADING_API_URL=https://... LADING_WEB_URL=https://... python -m deploy.smoke [--verify]

Checks /health, /scenarios and one /plan on the live API, then loads the Vercel page, confirms its bundle
points at that API and that the API's CORS answers the page's origin. With --verify it plans every
curated scenario and runs each of its disruptions live; a scenario whose runs all pass the validator
gets today's date in `live_verified` in scenarios/curated/index.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

INDEX = Path(__file__).resolve().parent.parent / "scenarios" / "curated" / "index.json"


def _request(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, Any, dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            ctype = resp.headers.get("content-type", "")
            return resp.status, json.loads(raw) if "json" in ctype else raw.decode(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    api = os.environ["LADING_API_URL"].rstrip("/")
    web = os.environ["LADING_WEB_URL"].rstrip("/")
    results = []

    status, body, _ = _request("GET", f"{api}/health")
    results.append(check("api /health", status == 200 and body.get("status") == "ok", str(body)[:120]))
    status, scenarios, _ = _request("GET", f"{api}/scenarios")
    results.append(check("api /scenarios", status == 200 and len(scenarios) >= 1, f"{len(scenarios)} curated"))
    started = time.perf_counter()
    status, plan, _ = _request("POST", f"{api}/plan", {"scenario_id": scenarios[0]["id"]})
    results.append(check(
        "api /plan", status == 200 and plan["lading"]["validation"]["status"] == "PASS",
        f"{scenarios[0]['id']} in {time.perf_counter() - started:.1f}s",
    ))

    status, html, _ = _request("GET", f"{web}/")
    bundle = re.search(r'src="(/assets/[^"]+\.js)"', html) if isinstance(html, str) else None
    results.append(check("web loads", status == 200 and bundle is not None))
    if bundle:
        _, js, _ = _request("GET", f"{web}{bundle.group(1)}")
        results.append(check("web bundle targets the live API", isinstance(js, str) and api in js))
    status, _, headers = _request("OPTIONS", f"{api}/plan", headers={"origin": web, "access-control-request-method": "POST"})
    allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
    results.append(check("api CORS allows the web origin", allowed == web, f"allow-origin={allowed}"))

    if args.verify:
        index = json.loads(INDEX.read_text())
        today = dt.date.today().isoformat()
        for entry in index["scenarios"]:
            sid = entry["id"]
            started = time.perf_counter()
            status, plan, _ = _request("POST", f"{api}/plan", {"scenario_id": sid})
            ok = status == 200 and plan["lading"]["validation"]["status"] == "PASS"
            elapsed = time.perf_counter() - started
            replans = []
            for i in range(len(entry.get("disruptions", []))):
                t0 = time.perf_counter()
                status, rp, _ = _request("POST", f"{api}/replan", {"scenario_id": sid, "disruption_index": i})
                replans.append(time.perf_counter() - t0)
                ok = ok and status == 200 and rp["lading"]["validation"]["status"] == "PASS"
                time.sleep(3.5)
            results.append(check(f"live verify {sid}", ok, f"plan {elapsed:.1f}s, replans {', '.join(f'{x:.1f}s' for x in replans)}"))
            if ok:
                entry["live_verified"] = today
                entry["expected_solve_s"] = round(elapsed, 1)
            time.sleep(3.5)
        INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
