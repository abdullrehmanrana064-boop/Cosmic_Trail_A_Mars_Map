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
    ("What does REMS measure?", "weather"),
    ("Where does the weather data come from?", "weather"),
    ("Is the temperature the same across the whole crater?", "weather"),
    ("What is the ground temperature?", "weather"),
    ("How much UV is there?", "weather"),
    ("What's the humidity?", "weather"),
    ("What is the air pressure?", "weather"),
    # thermal / dunes along the route
    ("Is the route hot?", "route_thermal"),
    ("Temperature on this path?", "route_thermal"),
    ("Will my route cross the dunes?", "route_thermal"),
    # NASA mission knowledge (app/mars_kb.py)
    ("What instruments does Curiosity have?", "kb"),
    ("What does ChemCam do?", "kb"),
    ("What does CheMin do?", "kb"),
    ("What does SAM do?", "kb"),
    ("What does RAD measure?", "kb"),
    ("What powers Curiosity?", "kb"),
    ("What is Curiosity?", "kb"),
    ("What is Gale Crater?", "kb"),
    ("Tell me about Mount Sharp", "kb"),
    ("Why are clays important?", "kb"),
    ("Was there ever water here?", "kb"),
    ("What's a sol?", "kb"),
    ("How cold does Mars get?", "kb"),
    ("How big is Mars?", "kb"),
    ("Tell me about the dust storm", "kb"),
    ("Are there dust devils?", "kb"),
    ("What makes driving hard for the rover?", "kb"),
    ("How do I plan a route?", "kb"),
    ("Why 15 degrees?", "kb"),
    ("Can I trust your answers?", "kb"),
    ("Are you AI?", "kb"),
    ("How much gravity is there?", "kb"),
    ("Why is Mars red?", "kb"),
    ("Can humans breathe on Mars?", "kb"),
    ("Is there life on Mars?", "kb"),
    ("How many moons does Mars have?", "kb"),
    ("What is Olympus Mons?", "kb"),
    ("Does Mars have seasons?", "kb"),
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
    assert "Am I safe here?" in d["reply"] and "ChemCam" in d["reply"]
    assert "no language model" in d["caveat"].lower()


def test_unknown_suggests_examples_and_help():
    d = _ask_no_data("blorp")
    assert d["intent"] == "unknown"
    assert "Am I safe here?" in d["reply"] and "help" in d["reply"].lower()


def test_windy_is_honest_about_missing_wind_data():
    d = _ask_no_data("How windy is it?")
    assert d["intent"] == "weather"
    assert d["confidence"] == "none"
    assert "No wind data" in d["reply"]


def test_weather_answers_stay_inside_nasa_material():
    """Hackathon rule: only NASA-provided data. No outside figures, no invented values."""
    for q in ("How cold is it?", "What does REMS measure?", "Is the temperature the same across the whole crater?",
              "What is the ground temperature?", "How much radiation is there?", "What's the humidity?"):
        d = _ask_no_data(q)
        text = d["reply"] + " " + d["data_source"] + " " + d["caveat"]
        assert "Hassler" not in text and "mSv" not in text
        assert "NASA" in d["data_source"]


def test_crater_wide_temperature_is_not_invented():
    d = _ask_no_data("Is the temperature the same across the whole crater?")
    assert "can't give one temperature for the whole crater" in d["reply"]
    assert "MarsWRF" in d["reply"] and "not a forecast" in d["caveat"].lower()


def test_ground_temperature_is_not_confused_with_air_temperature():
    d = _ask_no_data("What is the ground temperature?")
    assert d["confidence"] == "none" and "No ground-temperature data" in d["reply"]


def test_rems_answer_names_instrument_and_parameters():
    d = _ask_no_data("What does REMS measure?")
    for word in ("air temperature", "ground temperature", "pressure", "wind", "humidity", "UV"):
        assert word in d["reply"]
    assert "Bradbury Landing" in d["reply"] and "Kelvin" in d["caveat"]


# ---- conversational shape + NASA knowledge base ----

NO_DATA_INTENTS = ("weather", "kb", "help")
NO_DATA_QUESTIONS = [q for q, i in DEMO_QUESTIONS if i in NO_DATA_INTENTS]


def test_every_answer_ends_with_a_follow_up_question_and_chips():
    for q in NO_DATA_QUESTIONS:
        d = _ask_no_data(q)
        assert d["follow_up"] and d["follow_up"].endswith("?"), q
        assert d["reply"].rstrip().endswith(d["follow_up"]), q
        assert d["suggestions"], q


def test_replies_are_short_paragraphs():
    for q in NO_DATA_QUESTIONS:
        d = _ask_no_data(q)
        assert len(d["reply"]) < 900, q


def test_kb_entries_cite_sources_and_stay_nasa_only():
    from app.mars_kb import ENTRIES
    assert len({e.key for e in ENTRIES}) == len(ENTRIES)
    for e in ENTRIES:
        assert e.answer and e.why and e.follow_up.endswith("?") and e.chips, e.key
        assert e.sources, e.key
        if e.nasa:
            assert all(u.startswith("https://") and ("nasa.gov" in u) for _, u in e.sources), e.key


def test_kb_answer_carries_source_links():
    d = _ask_no_data("What does ChemCam do?")
    assert d["intent"] == "kb" and d["confidence"] == "high"
    assert d["data"]["sources"][0]["url"].startswith("https://")
    assert "9 m" in d["reply"]


def test_kb_does_not_invent_figures_nasa_pages_lack():
    d = _ask_no_data("How much gravity is there?")
    assert d["confidence"] == "none" and "won't guess" in d["reply"]
    assert "3.7" not in d["reply"] and "m/s" not in d["reply"]


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



def test_added_mars_topics_answer_with_cited_nasa_sources():
    cases = {
        "Why is Mars red?": ("mars_red", "iron"),
        "Can humans breathe on Mars?": ("human_breathing", "carbon dioxide"),
        "Is there life on Mars?": ("life_on_mars", "No confirmed evidence"),
        "How many moons does Mars have?": ("mars_moons", "Phobos and Deimos"),
        "What is Olympus Mons?": ("olympus_mons", "largest volcano"),
        "Does Mars have seasons?": ("mars_seasons", "axis is tilted"),
    }
    for question, (topic, phrase) in cases.items():
        d = _ask_no_data(question)
        assert d["intent"] == "kb"
        assert d["data"]["topic"] == topic
        assert phrase.lower() in d["reply"].lower()
        assert d["data"]["sources"]
        assert all(s["url"].startswith("https://") and "nasa.gov" in s["url"] for s in d["data"]["sources"])
        assert d["follow_up"] and d["follow_up"].endswith("?")
