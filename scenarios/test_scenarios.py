import json
import re
from pathlib import Path

import pytest

from errors import LadingError, State
from scenarios import organizer
from scenarios.loader import SCHEMA_PATH, load, parse
from scenarios.model import json_schema
from scenarios.scenario_gen import ASSUMPTIONS_PATH, FAMILIES, assumptions, dump, generate

ROOT = Path(__file__).resolve().parent.parent


def raw(seed: int = 3, family: str = "base") -> dict:
    return json.loads(dump(generate(seed, family)))


def test_committed_schema_matches_models():
    assert json.loads(SCHEMA_PATH.read_text()) == json.loads(json.dumps(json_schema()))


def test_generator_is_deterministic():
    assert dump(generate(11)) == dump(generate(11))
    assert dump(generate(11)) != dump(generate(12))


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_round_trips_through_loader(family):
    scenario = parse(raw(4, family))
    assert scenario.family == family
    assert scenario.synthetic is True


def test_generated_sizes_stay_inside_disclosed_ranges():
    a = assumptions()
    for seed in range(20):
        s = generate(seed)
        assert a["batch_count"][0] <= len(s.batches) <= a["batch_count"][1]
        assert a["market_count"][0] <= len(s.markets) <= a["market_count"][1]
        assert a["truck_count"][0] <= len(s.trucks) <= a["truck_count"][1]
        assert all(a["batch_kg"][0] <= b.kg <= a["batch_kg"][1] for b in s.batches)


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda r: r["batches"][3].__setitem__("kg", -5), "batches[3].kg"),
        (lambda r: r["batches"][0].pop("shelf_life_h"), "batches[0]"),
        (lambda r: r["batches"][2].__setitem__("commodity_id", "durian"), "batches[2].commodity_id"),
        (lambda r: r["markets"][1].__setitem__("surprise", 1), "markets[1]"),
        (lambda r: r["batches"][1].__setitem__("id", r["batches"][0]["id"]), "batches[1].id"),
        (lambda r: r["policy"].__setitem__("discount_levels", [0.1, 0.2]), "policy.discount_levels"),
        (lambda r: r["controls"]["locks"].append({"batch_id": "b01", "market_id": "nowhere", "slot_id": "s0"}),
         "controls.locks[0].market_id"),
    ],
)
def test_loader_rejects_bad_input_with_exact_field_path(mutate, path):
    r = raw()
    mutate(r)
    with pytest.raises(LadingError) as exc:
        parse(r)
    assert exc.value.state is State.SCHEMA_INVALID
    assert exc.value.path == path


def test_loader_rejects_non_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(LadingError) as exc:
        load(bad)
    assert exc.value.state is State.SCHEMA_INVALID


def test_every_assumption_is_mirrored_in_docs():
    doc = (ROOT / "docs" / "ASSUMPTIONS.md").read_text()
    a = json.loads(ASSUMPTIONS_PATH.read_text())
    keys = [k for k in a if k not in {"note", "version", "commodities", "hubs", "families", "shocks"}]
    keys += list(a["shocks"]) + list(a["families"])
    keys += [f"{c}.{field}" for c, spec in a["commodities"].items() for field in spec if field != "name"]
    missing = [k for k in keys if not re.search(rf"`{re.escape(k)}`", doc)]
    assert not missing, f"assumptions missing from docs/ASSUMPTIONS.md: {missing}"


def test_organizer_adapter_loads_lading_format_and_rejects_unknown(tmp_path):
    assert not organizer.available(tmp_path)
    good = raw()
    good["source"] = "organizer"
    (tmp_path / "a.json").write_text(json.dumps(good))
    assert organizer.available(tmp_path)
    assert [s.source for s in organizer.load_all(tmp_path)] == ["organizer"]
    (tmp_path / "b.json").write_text(json.dumps({"format": "spreadsheet-v9"}))
    with pytest.raises(LadingError) as exc:
        organizer.load_all(tmp_path)
    assert exc.value.state is State.SCHEMA_INVALID
