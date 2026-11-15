"""Demo questions for ARIA: each must reach the intended intent (and answer sensibly).

The intent checks need no data. The endpoint checks run only when the real HiRISE dataset is present.
Keep this list in sync with DEMO_QUESTIONS.md.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.assistant import Assistant, detect_intent

REAL_DS = "hirise_gale"
BRADBURY = {"current_lon": 137.4417, "current_lat": -4.5895}

# (question, expected intent)
DEMO_QUESTIONS: list[tuple[str, str]] = [
    # slope — "is it safe to walk here?"
    ("Am I safe here?", "slope"),
    ("Is it safe to walk north?", "slope"),
    ("How steep is it here?", "slope"),
    ("Can I climb east from here?", "slope"),
    ("What is the slope here?", "slope"),
    ("Is this spot safe to walk on?", "slope"),
    # hazards
    ("Any hazards nearby?", "hazard"),
    ("Is there anything dangerous around me?", "hazard"),
    ("Are there cliffs near here?", "hazard"),
    ("What should I avoid?", "hazard"),
    # elevation
    ("What is the elevation here?", "elevation"),
    ("How high am I?", "elevation"),
    ("What's the altitude?", "elevation"),
    # distance
    ("How far is Mount Sharp?", "distance"),
    ("How far is Bradbury Landing?", "distance"),
    ("What is the distance to Aeolis Palus?", "distance"),
    # route
    ("Analyze my route", "route_safety"),
    ("Is my route safe?", "route_safety"),
    ("Is my path safe?", "route_safety"),
    ("How long is my route?", "route_safety"),
    # path to clay
    ("What's the best path to clay?", "go_to_clay"),
    ("Take me to Yellowknife Bay", "go_to_clay"),
    ("Where is the nearest clay?", "go_to_clay"),
    # minerals / geology
    ("What minerals are nearby?", "minerals"),
    ("Is there any sulfate around?", "minerals"),
    ("Tell me about the geology here", "minerals"),
    ("Are there clays at Gale Crater?", "minerals"),
    # what is here?
    ("What's here?", "place_info"),
    ("Where am I?", "place_info"),
    ("Tell me about this place", "place_info"),
    # weather (published figures only)
    ("How cold is it?", "weather"),
    ("What's the temperature?", "weather"),
    ("How much radiation is there?", "weather"),
    ("What's the weather like?", "weather"),
    ("How windy is it?", "weather"),
    # thermal / dunes along the route
    ("Is the route hot?", "route_thermal"),
    ("Temperature on this path?", "route_thermal"),
    ("Will my route cross the dunes?", "route_thermal"),
    # help / greeting
    ("What can you do?", "help"),
    ("help", "help"),
    ("Hello", "help"),
    ("Who are you?", "help"),
]


def test_there_are_at_least_30_demo_questions():
    assert len(DEMO_QUESTIONS) >= 30
    assert len({q for q, _ in DEMO_QUESTIONS}) == len(DEMO_QUESTIONS)   # no duplicates


@pytest.mark.parametrize("question,intent", DEMO_QUESTIONS)
def test_demo_question_reaches_intent(question, intent):
    assert detect_intent(question) == intent


# ---- answers that need no terrain data ----

def _ask_no_data(message: str) -> dict:
    return Assistant(ds=None).answer(message, BRADBURY["current_lon"], BRADBURY["current_lat"])


def test_help_lists_example_questions():
    d = _ask_no_data("What can you do?")
    assert d["intent"] == "help"
    assert "Am I safe here?" in d["reply"] and "How cold is it?" in d["reply"]
    assert "no language model" in d["caveat"].lower()


def test_unknown_suggests_examples_and_help():
    d = _ask_no_data("blorp")
    assert d["intent"] == "unknown"
    assert "Am I safe here?" in d["reply"] and "help" in d["reply"].lower()


def test_windy_is_honest_about_missing_wind_data():
    d = _ask_no_data("How windy is it?")
    assert d["intent"] == "weather"
    assert d["confidence"] == "none"
    assert "No wind or pressure data" in d["reply"]


# ---- full endpoint (skipped without the real dataset) ----

@pytest_asyncio.fixture(scope="module")
async def client():
    from app.main import app, _load_datasets, DATASETS
    if not DATASETS:
        _load_datasets()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.parametrize("question,intent", DEMO_QUESTIONS)
async def test_demo_question_endpoint(client, question, intent):
    r = await client.get("/api/datasets")
    if REAL_DS not in [d["id"] for d in r.json()["datasets"]]:
        pytest.skip(f"{REAL_DS} dataset not present")
    r = await client.post("/api/assistant/chat",
                          json={"message": question, "context": {"dataset_id": REAL_DS, **BRADBURY}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == intent
    assert d["reply"].strip()
    assert d["data_source"]
    assert d["confidence"] in ("high", "medium", "low", "none")
