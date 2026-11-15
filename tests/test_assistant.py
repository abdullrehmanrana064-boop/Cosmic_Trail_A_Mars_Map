"""Tests for ARIA, the rule-based assistant (POST /api/assistant/chat)."""
from __future__ import annotations

import re

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.assistant import detect_direction, detect_intent

pytestmark = pytest.mark.asyncio

REAL_DS = "hirise_gale"
BRADBURY = {"current_lon": 137.4417, "current_lat": -4.5895}


@pytest_asyncio.fixture(scope="module")
async def client():
    from app.main import app, _load_datasets, DATASETS
    if not DATASETS:
        _load_datasets()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _require_real(client):
    r = await client.get("/api/datasets")
    if REAL_DS not in [d["id"] for d in r.json()["datasets"]]:
        pytest.skip(f"{REAL_DS} dataset not present")


async def _ask(client, message, **context):
    r = await client.post("/api/assistant/chat", json={"message": message, "context": {"dataset_id": REAL_DS, **context}})
    assert r.status_code == 200, r.text
    return r.json()


# ---- keyword detection (no data needed) ----

async def test_intent_detection():
    assert detect_intent("How steep is it here?") == "slope"
    assert detect_intent("What is the elevation?") == "elevation"
    assert detect_intent("Any hazards to avoid?") == "hazard"
    assert detect_intent("Tell me about the clay minerals") == "minerals"
    assert detect_intent("What's the temperature today?") == "weather"
    assert detect_intent("Analyze my route") == "route_safety"
    assert detect_intent("How far is Mount Sharp?") == "distance"
    assert detect_intent("blorp") == "unknown"
    assert detect_direction("walk north-east please") == ("northeast", 45.0)
    assert detect_direction("go north") == ("north", 0.0)


# ---- endpoint ----

async def test_slope_here_uses_grid_and_thresholds(client):
    await _require_real(client)
    d = await _ask(client, "How steep is it here?", **BRADBURY)
    assert d["intent"] == "slope"
    assert d["data_source"] in ("HiRISE DTM", "USGS Gale DEM (gap fill)")
    assert 0 <= d["data"]["slope_deg"] < 90
    assert d["data"]["max_deg"] >= d["data"]["mean_deg"]
    assert "10°" in d["reply"] or "15°" in d["reply"]
    assert d["engine"].startswith("rule-based")


async def test_walk_north_from_bradbury_transect(client):
    """The spec's example question: a 500 m line to the north, analysed from the grid."""
    await _require_real(client)
    d = await _ask(client, "Is it safe to walk north from Bradbury Landing?", current_lon=137.5, current_lat=-4.55)
    assert d["intent"] == "slope"
    assert d["location"] == {"lon": 137.4417, "lat": -4.5895}       # place named in the message wins
    assert d["data"]["direction"] == "north"
    assert 0 < d["data"]["length_m"] <= 500
    assert "elevation_change_m" in d["data"]
    # never declares terrain safe
    assert not re.search(r"\b(is|it's|route is) (safe|clear)\b", d["reply"].lower())


async def test_elevation_matches_lookup(client):
    await _require_real(client)
    d = await _ask(client, "What's the elevation here?", **BRADBURY)
    look = (await client.get(f"/api/datasets/{REAL_DS}/lookup", params={"lon": 137.4417, "lat": -4.5895})).json()
    assert d["intent"] == "elevation"
    assert d["data"]["elevation_m"] == pytest.approx(look["elevation_m"], abs=0.01)
    assert "areoid" in d["reply"]


async def test_hazard_check_reports_counts(client):
    await _require_real(client)
    d = await _ask(client, "Any hazards to avoid around here?", **BRADBURY)
    assert d["intent"] == "hazard"
    assert d["data"]["radius_m"] == 250
    assert d["data"]["cells_above_max"] >= 0 and d["data"]["cells_above_caution"] >= d["data"]["cells_above_max"]


async def test_route_analysis_with_and_without_route(client):
    await _require_real(client)
    none = await _ask(client, "Analyze my route", **BRADBURY)
    assert none["confidence"] == "none" and "Find Route" in none["reply"]
    route = (await client.post("/api/route", json={
        "dataset_id": REAL_DS, "start": {"lon": 137.4417, "lat": -4.5895},
        "destination": {"lon": 137.47, "lat": -4.58}, "mode": "terrain"})).json()["routes"]["terrain"]
    summary = {k: route[k] for k in ("mode", "cells", "slope_max_deg", "slope_mean_deg", "cells_above_caution",
                                     "surface_length_3d_m", "planimetric_length_m", "elevation_gain_m",
                                     "elevation_loss_m", "data_coverage_on_route")}
    d = await _ask(client, "Analyze my route", last_route=summary, **BRADBURY)
    assert d["intent"] == "route_safety" and d["confidence"] == "high"
    assert f"{route['surface_length_3d_m'] / 1000:.2f} km" in d["reply"]
    assert f"{route['slope_max_deg']:.1f}°" in d["reply"]


async def test_minerals_nearby_uses_detection_sites_and_cards(client):
    await _require_real(client)
    d = await _ask(client, "What minerals are nearby?", **BRADBURY)
    assert d["intent"] == "minerals"
    assert "Yellowknife" in d["reply"] and "smectite" in d["reply"]
    if "nearest_sites" in d["data"]:
        assert "CRISM" in d["data_source"]
        dists = [s["distance_km"] for s in d["data"]["nearest_sites"]]
        assert dists == sorted(dists)


async def test_weather_gives_cited_published_figures(client):
    await _require_real(client)
    d = await _ask(client, "What's the weather and radiation like?", **BRADBURY)
    assert d["intent"] == "weather"
    assert d["confidence"] == "medium"
    assert "-70" in d["reply"] and "Hassler" in d["reply"]
    assert "PIA16913" in d["data_source"]
    assert "not live" in d["caveat"].lower()


# ---- weather answers (no dataset needed: Assistant.weather uses only the cited facts) ----

def _weather(message: str) -> dict:
    from app.assistant import Assistant
    return Assistant(ds=None).answer(message, 137.4417, -4.5895)


async def test_weather_temperature_is_cited_and_never_live():
    d = _weather("What's the temperature at Gale?")
    assert d["intent"] == "weather"
    assert "0 °C" in d["reply"] and "-70 °C" in d["reply"]
    assert "PIA16913" in d["data_source"]
    assert d["data"]["source_url"].startswith("https://www.jpl.nasa.gov/")
    assert "not live" in d["caveat"].lower() and "forecast" in d["caveat"].lower()


async def test_weather_radiation_only_uses_rad_figure():
    d = _weather("How much radiation is there?")
    assert d["intent"] == "weather"
    assert "0.64" in d["reply"] and "Hassler" in d["data_source"]


async def test_weather_wind_and_pressure_stay_honest():
    d = _weather("What is the wind speed?")
    assert d["intent"] == "weather"
    assert d["confidence"] == "none"
    assert "No wind or pressure data" in d["reply"]


async def test_outside_grid_falls_back_or_declines(client):
    await _require_real(client)
    d = await _ask(client, "How steep is it here?", current_lon=137.85, current_lat=-5.08)   # Mount Sharp
    assert d["intent"] == "outside_grid"
    assert d["confidence"] in ("low", "none")
    assert "outside the 5 m routing grid" in d["reply"]


async def test_distance_to_named_place(client):
    await _require_real(client)
    d = await _ask(client, "How far is Mount Sharp?", **BRADBURY)
    assert d["intent"] == "distance"
    assert 30_000 < d["data"]["distance_m"] < 40_000      # Bradbury → Aeolis Mons card point ≈ 33 km


async def test_validation_errors(client):
    r = await client.post("/api/assistant/chat", json={"message": ""})
    assert r.status_code == 422
    r = await client.post("/api/assistant/chat", json={"message": "slope?", "context": {"current_lon": 137.4, "current_lat": 95}})
    assert r.status_code == 400


async def test_replies_are_verdict_first_and_short(client):
    """Plain-language format: verdict line, one sentence, at most 3 numbers (+ optional warning line)."""
    await _require_real(client)
    verdicts = ("✅", "⚠️", "❌", "🔬", "📍", "📏", "❓", "📚")
    for q in ("Am I safe here?", "Any hazards?", "What minerals are nearby?", "What's the elevation?",
              "Is it safe to walk north?", "How far is Mount Sharp?"):
        d = await _ask(client, q, **BRADBURY)
        lines = d["reply"].split("\n")
        assert lines[0].startswith(verdicts), (q, lines[0])
        assert 2 <= len(lines) <= 4, (q, lines)
        if len(lines) >= 3:
            assert lines[2].count(" · ") <= 2, (q, lines[2])     # at most three key numbers
    d = await _ask(client, "Any hazards?", **BRADBURY)
    assert d["intent"] == "hazard"                                # plural keyword now recognised


# ---- dynamic, location-specific answers (app/context.py) ----

YKB = (137.4453, -4.5890)


async def test_location_intents_win_over_keywords():
    assert detect_intent("Best path to clay?") == "go_to_clay"          # not route_safety ("path") or minerals ("clay")
    assert detect_intent("How do I reach Yellowknife Bay?") == "go_to_clay"
    assert detect_intent("Where is the nearest clay?") == "go_to_clay"
    assert detect_intent("What's here?") == "place_info"
    assert detect_intent("Where am I?") == "place_info"
    assert detect_intent("Is this safe?") == "slope"
    assert detect_intent("What minerals are nearby?") == "minerals"      # unchanged


async def test_is_this_safe_adds_location_context(client):
    await _require_real(client)
    d = await _ask(client, "Is this safe?", **BRADBURY)
    assert d["intent"] == "slope"
    assert d["data"]["data_quality"] in ("hirise", "usgs", "mola")
    assert "loaded" in d["data"]["dunes"]
    last = d["reply"].split("\n")[-1]
    assert ">15° slope" in last
    if not d["data"]["dunes"]["loaded"]:                                  # no dune boundary bundled: say so
        assert "dune map not loaded" in last and "away from dunes" not in d["reply"]


async def test_whats_here_reports_unit_elevation_minerals_coverage(client):
    await _require_real(client)
    d = await _ask(client, "What's here?", **BRADBURY)
    look = (await client.get(f"/api/datasets/{REAL_DS}/lookup", params={"lon": 137.4417, "lat": -4.5895})).json()
    assert d["intent"] == "place_info"
    assert d["data"]["elevation_m"] == pytest.approx(look["elevation_m"], abs=0.1)
    assert d["data"]["geologic_unit"]["unit"] == "eHt"                   # inside the eHt rectangle
    assert d["data"]["hirise_coverage"] is (look["elevation_source"].startswith("HiRISE"))
    assert d["data"]["nearest_confirmed_clay"]["name"] == "Yellowknife Bay"
    assert "eHt" in d["reply"] and "HiRISE coverage" in d["reply"]


async def test_best_path_to_clay_gives_direction_terrain_and_action(client):
    await _require_real(client)
    d = await _ask(client, "Best path to clay?", current_lon=137.43, current_lat=-4.60)
    assert d["intent"] == "go_to_clay"
    t = d["data"]["target"]
    assert t["name"] == "Yellowknife Bay" and t["bearing"] == "north-east"
    assert 900 < t["distance_m"] < 1400
    assert d["data"]["action"] == {"type": "set_destination", "lon": YKB[0], "lat": YKB[1], "label": "Yellowknife Bay"}
    assert d["data"]["terrain_between"]["sampled"] > 100
    assert d["reply"].startswith("🧭 Yellowknife Bay is") and "km NE" in d["reply"].split("\n")[0]
    at = await _ask(client, "Best path to clay?", current_lon=YKB[0], current_lat=YKB[1])
    assert at["reply"].startswith("🔬 You're at Yellowknife Bay")


async def test_route_response_includes_location_context(client):
    await _require_real(client)
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS, "start": {"lon": 137.4417, "lat": -4.5895},
        "destination": {"lon": 137.47, "lat": -4.58}, "mode": "terrain"})
    assert r.status_code == 200, r.text
    ctx = r.json()["routes"]["terrain"]["context"]
    assert ctx["science"]["text"].startswith("🔬 Science:")
    assert ctx["science"]["site"] == "Yellowknife Bay" and ctx["science"]["distance_m"] < 1000
    assert ctx["thermal"]["text"].startswith("🌡️ Thermal:")
    assert 0 <= ctx["data"]["hirise_pct"] <= 100 and ctx["data"]["text"].startswith("📡 Data:")
    if not ctx["thermal"]["checked"]:
        assert "not checked" in ctx["thermal"]["text"]


async def test_dune_checks_work_once_a_boundary_is_added(monkeypatch):
    """No dune boundary ships, but the check must work as soon as one is added to hazard_zones.geojson."""
    from app import context
    square = {"type": "Feature", "properties": {"kind": "dune", "name": "Test dunes"},
              "geometry": {"type": "Polygon", "coordinates": [[[137.40, -4.70], [137.42, -4.70], [137.42, -4.72],
                                                               [137.40, -4.72], [137.40, -4.70]]]}}
    monkeypatch.setattr(context, "_dunes", lambda: [square])
    inside = context.dune_status(137.41, -4.71)
    assert inside["loaded"] and inside["inside"]
    assert "on Test dunes sand" in context.dune_line(inside)
    far = context.dune_status(137.4417, -4.5895)
    assert not far["inside"] and 6_000 < far["distance_m"] < 7_500 and "away from dunes" in context.dune_line(far)


async def test_temperature_on_path_gives_dune_thermal_not_weather(client):
    """Regression: 'Temperature on this path?' used to fall through to the weather/radiation reply."""
    await _require_real(client)
    assert detect_intent("Temperature on this path?") == "route_thermal"
    assert detect_intent("What's the temperature today?") == "weather"           # unchanged
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS, "start": {"lon": 137.44, "lat": -4.62},
        "destination": {"lon": 137.45, "lat": -4.70}, "mode": "terrain"})
    assert r.status_code == 200, r.text
    thermal = r.json()["routes"]["terrain"]["context"]["thermal"]
    d = await _ask(client, "Temperature on this path?", current_lon=137.44, current_lat=-4.62,
                   last_route={"mode": "terrain", "thermal": thermal})
    assert d["intent"] == "route_thermal" and "Hassler" not in d["reply"]
    if thermal["checked"]:
        assert thermal["crossings"] and "HIGH thermal risk" in d["reply"]
        assert "Cross before 10:00" in d["reply"] and "+27°C" in d["reply"]
