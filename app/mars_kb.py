"""ARIA's Mars mission knowledge base: short, cited answers to the questions people ask most.

Hackathon rule: ARIA may only state what NASA-provided material says. Every NASA entry below was written
from the NASA page named in its `sources`, read on 2026-11-15; where a page did not give a figure, the entry
does not either (for example the page on Mars facts gives no gravity or radio-delay number, so ARIA says it
has none). A few entries explain how COSMIC TRAIL itself works; those cite the project documentation instead
and are marked `nasa=False`.

Each entry is conversational on purpose: the direct answer first, one sentence of explanation, one
suggestion, and a follow-up question. Keep every part to a sentence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---- NASA sources (all read 2026-11-15) ----------------------------------------------------------------
ARES = ("NASA ARES: The Curiosity Rover at Gale Crater", "https://ares.jsc.nasa.gov/missions/msl/")
JPL_YK = ("NASA/JPL: Rover finds conditions once suited for ancient life (12 Mar 2013)",
          "https://www.jpl.nasa.gov/news/nasa-rover-finds-conditions-once-suited-for-ancient-life-on-mars/")
MARS_FACTS = ("NASA Science: Mars facts", "https://science.nasa.gov/mars/facts/")
GSFC = ("NASA Goddard: Curiosity instruments", "https://science.gsfc.nasa.gov/sam/curiosity.html")
JPL_DRIVE = ("NASA/JPL: Curiosity checking possible smoother route",
             "https://www.jpl.nasa.gov/news/curiosity-mars-rover-checking-possible-smoother-route/")
GODDARD_DUST = ("NASA Goddard: How a tiny Curiosity motor identified a massive Martian dust storm (2018)",
                "https://www.nasa.gov/feature/goddard/2018/how-a-tiny-curiosity-motor-identified-a-massive-martian-dust-storm")
DUST_DEVIL = ("NASA Photojournal: Martian dust devil action in Gale Crater, sol 1597",
              "https://science.nasa.gov/photojournal/martian-dust-devil-action-in-gale-crater-sol-1597/")
PIA16913 = ("NASA Science: Steady temperatures at Mars' Gale Crater (PIA16913)",
            "https://science.nasa.gov/resource/steady-temperatures-at-mars-gale-crater/")
DOCS = ("COSMIC TRAIL documentation (README, SCIENTIFIC_LIMITATIONS.md)", "")


@dataclass(frozen=True)
class KB:
    key: str
    patterns: tuple[str, ...]          # regexes tried on the lower-cased message
    answer: str                        # the direct answer, first
    why: str                           # one sentence of explanation
    tip: str | None                    # one suggestion
    follow_up: str                     # a question that keeps the conversation going
    chips: tuple[str, ...]             # tappable next questions
    sources: tuple[tuple[str, str], ...]
    caveat: str | None = None
    nasa: bool = True


def _instrument(key: str, pattern: str, answer: str, why: str, chips: tuple[str, ...]) -> KB:
    return KB(key, (pattern,), answer, why, "Ask me about another instrument any time.",
              "Want to hear about one of the others?", chips, (GSFC,))


ENTRIES: tuple[KB, ...] = (
    # ---- Curiosity and its instruments -----------------------------------------------------------
    KB("instruments", (r"\binstruments?\b", r"\bpayload\b", r"\bwhat (does|is) curiosity (carry|have|equipped)\b"),
       "Curiosity carries a suite of science instruments, including ChemCam, CheMin, SAM, REMS and RAD.",
       "Between them they study rocks and minerals (ChemCam, CheMin, APXS), chemistry (SAM), weather (REMS) and radiation (RAD).",
       "Ask about any one of them, for example ChemCam or CheMin.",
       "Which one would you like to hear about?",
       ("What does ChemCam do?", "What does CheMin do?", "What does RAD measure?"), (GSFC,)),
    _instrument("chemcam", r"\bchem ?cam\b",
                "ChemCam uses a laser to study the composition and texture of rocks and soil from up to 9 m (30 ft) away.",
                "Other instruments, like CheMin, identify the minerals in samples, so the two complement each other.",
                ("What does CheMin do?", "What does SAM do?")),
    _instrument("chemin", r"\bchemin\b",
                "CheMin identifies and measures the minerals in rocks and soil.",
                "SAM adds the chemistry side by measuring carbon, oxygen, hydrogen and nitrogen.",
                ("What does SAM do?", "What does ChemCam do?")),
    _instrument("sam", r"\bsam\b|\bsample analysis\b",
                "SAM is a suite of three instruments (a gas chromatograph, a quadrupole mass spectrometer and a tunable laser "
                "spectrometer) that measures carbon, oxygen, hydrogen and nitrogen.",
                "CheMin works alongside it, identifying the minerals in rocks and soil.",
                ("What does CheMin do?", "What does RAD measure?")),
    KB("rad", (r"\brad\b", r"\bradiation (detector|assessment)\b"),
       "RAD measures high-energy radiation at the Martian surface, from space and from the surface and atmosphere.",
       "COSMIC TRAIL doesn't include RAD readings, so I can't give you a radiation figure.",
       "REMS, the weather station, measures UV radiation too, but I don't have those values loaded either.",
       "Want to know what REMS does measure?", ("What does REMS measure?", "How cold is it?"), (GSFC,)),
    _instrument("mahli", r"\bmahli\b", "MAHLI works like a geologist's hand lens, taking close-up views of rock minerals, textures and surfaces.",
                "Mastcam takes the wider colour images and videos that can be combined into panoramas.",
                ("What does Mastcam do?", "What does ChemCam do?")),
    _instrument("mastcam", r"\bmast ?cam\b", "Mastcam takes colour videos and images that can be combined into panoramas.",
                "MAHLI handles the close-ups, like a geologist's hand lens.",
                ("What does MAHLI do?", "What does ChemCam do?")),
    _instrument("apxs", r"\bapxs\b", "APXS measures the abundance of elements in rocks and soils.",
                "CheMin identifies the minerals, so together they describe both the elements and the minerals.",
                ("What does CheMin do?", "What does SAM do?")),
    _instrument("dan", r"\bdan\b", "DAN detects escaping neutrons; slower neutrons may point to subsurface water or ice.",
                "It is one of the instruments listed alongside ChemCam, CheMin and SAM.",
                ("What instruments does Curiosity have?", "What does SAM do?")),
    _instrument("mardi", r"\bmardi\b", "MARDI took colour video of the rover's descent during landing.",
                "It is one of Curiosity's instruments, alongside the camera and chemistry tools.",
                ("What instruments does Curiosity have?", "What does Mastcam do?")),
    KB("power", (r"\b(what )?powers?\b.*\b(curiosity|rover)\b", r"\b(curiosity|rover)\b.*\b(powered|power source)\b",
                 r"\bnuclear\b", r"\bsolar panels?\b"),
       "Curiosity runs on a radioisotope power generator, not solar panels.",
       "That is why the 2018 global dust storm, which starved Opportunity's solar panels of sunlight, didn't affect its operations.",
       "NASA designed it to run for at least one Martian year, which is 687 Earth days.",
       "Want to hear about that dust storm?", ("Tell me about the dust storm", "What is Curiosity?"), (GSFC, GODDARD_DUST)),
    KB("curiosity", (r"\b(what|who) is curiosity\b", r"\babout (the )?curiosity\b", r"\bhow (big|large) is (curiosity|the rover)\b",
                     r"\bwhat is the rover\b"),
       "Curiosity is a NASA rover about the size of a small SUV that landed in Gale Crater on August 6, 2012.",
       "It carries instruments to study rocks, weather and radiation, and one of its science goals is to assess the "
       "habitability of ancient and modern Martian environments.",
       "COSMIC TRAIL's terrain, minerals and weather answers are all built around its landing area.",
       "Would you like to hear about its instruments?", ("What instruments does Curiosity have?", "What powers Curiosity?"),
       (ARES, GSFC)),
    # ---- Gale Crater, Mount Sharp, clays and water -----------------------------------------------
    KB("gale", (r"\bwhat is gale( crater)?\b", r"\babout gale( crater)?\b", r"\bwhy gale\b", r"\bhow (big|wide|large) is (gale|the crater)\b",
                r"\bwhy (did|was)\b.*\b(land|landed|chosen)\b.*\b(gale|here)\b"),
       "Gale Crater is about 150 km wide and sits near the Martian equator, where Curiosity landed on August 6, 2012.",
       "NASA says the rocks at its centre contain minerals that are key to understanding ancient environments and climate change.",
       "At its centre is Mount Sharp, a mountain about 5 km high made of layered sedimentary rock.",
       "Want to hear what those layers can tell us?", ("Tell me about Mount Sharp", "Why are clays important?"), (ARES,)),
    KB("mount_sharp", (r"\b(what|tell me about|about|how (tall|high|big))\b.*\b(mount sharp|aeolis mons)\b",
                       r"\b(mount sharp|aeolis mons)\b.*\b(made of|tall|height)\b"),
       "Mount Sharp is a mountain about 5 km high at the centre of Gale Crater, made of layered sedimentary rock.",
       "Its lowest layers contain clay minerals, and sulfates lie above them, a sequence NASA says marks a major climatic "
       "change more than 3 billion years ago.",
       "You can see where it is on the map, and I can tell you how far it is from you.",
       "Want to know why clay minerals matter?", ("Why are clays important?", "How far is Mount Sharp?"), (ARES,)),
    KB("why_clay", (r"\bwhy\b.*\b(clays?|sulfates?)\b", r"\b(clays?|sulfates?)\b.*\b(important|matter|mean|tell us|form)\b",
                    r"\bwhat (is|are) (clays?|sulfates?)\b"),
       "On Earth, clay minerals generally form where there is abundant liquid water, so finding them points to a wetter past.",
       "On Mount Sharp the sulfates above the clays need less water to form and come from salty, possibly acidic solutions, "
       "and NASA says that sequence marks a major climate change more than 3 billion years ago.",
       "I can show you where Curiosity confirmed clays.",
       "Want me to point you to the nearest confirmed clay site?", ("Best path to clay?", "Tell me about Yellowknife Bay"),
       (ARES,)),
    KB("yellowknife", (r"^(?!.*\bhow far\b).*\byellowknife\b", r"\bhabitab", r"\bwas there (ever )?(life|water)\b",
                       r"\b(did|has) (curiosity|nasa) (find|found)\b.*\b(life|water)\b", r"\bancient (lake|river|life)\b"),
       "Yellowknife Bay is where Curiosity found conditions that could once have supported microbes, in what NASA describes "
       "as the end of an ancient river system or an intermittently wet lake bed.",
       "The drilled mudstone powder held sulfur, nitrogen, hydrogen, oxygen, phosphorus and carbon, clay minerals made up at "
       "least 20 percent of the sample, and the site wasn't harshly oxidizing, acidic or extremely salty.",
       "Habitable means life could have lived there, not that it did.",
       "Want me to check how far Yellowknife Bay is from you?", ("Best path to clay?", "Why are clays important?"),
       (JPL_YK,), caveat="NASA announced this in March 2013, after drilling the previous month."),
    # ---- Mars itself ------------------------------------------------------------------------------
    KB("sol", (r"\bwhat('s| is) a sol\b", r"\bsols?\b.*\b(mean|long|hours)\b", r"\blength of (a )?(mars |martian )?day\b",
               r"\bhow long is a (mars |martian )?day\b", r"\b(mars|martian) (day|year)\b"),
       "A sol is one Martian day, about 24.6 hours long.",
       "A Mars year lasts 669.6 sols, which is 687 Earth days.",
       "NASA's REMS weather records are grouped by sol and local time.",
       "Want to know how cold a typical sol gets at Gale Crater?", ("How cold is it?", "How big is Mars?"), (MARS_FACTS,)),
    KB("mars_cold", (r"\bhow (cold|hot|warm) (does|is) mars\b", r"\b(coldest|hottest)\b", r"\bmars temperatures?\b",
                     r"\btemperatures? (on|of) mars\b"),
       "Across the whole planet, NASA lists a maximum of about 20 °C and a minimum of about -153 °C.",
       "At Curiosity's site in Gale Crater, early-mission air temperatures had highs around 0 °C and lows around -70 °C.",
       "Remember that REMS readings come from the rover's location, not the whole crater.",
       "Want to know which instrument measures that?", ("What does REMS measure?", "What's a sol?"), (MARS_FACTS, PIA16913)),
    KB("mars_size", (r"\bhow (big|large) is mars\b", r"\bsize of mars\b", r"\bmars\b.*\b(moons?|phobos|deimos)\b",
                     r"\bhow far is mars from the sun\b", r"\bmars\b.*\b(distance|far)\b.*\bsun\b"),
       "Mars is about half the size of Earth, with a radius of about 3,390 km, and it has two moons, Phobos and Deimos.",
       "On average it orbits about 228 million km (1.5 AU) from the Sun.",
       "A Mars day, called a sol, lasts about 24.6 hours.",
       "Want to hear about its atmosphere?", ("What is the atmosphere like?", "What's a sol?"), (MARS_FACTS,)),
    KB("atmosphere", (r"\bmars('s| )?\s*atmosphere\b", r"\bwhat is the atmosphere\b", r"\batmosphere (like|made)\b"),
       "Mars' atmosphere is thin and made mostly of carbon dioxide, nitrogen and argon.",
       "Curiosity's REMS instrument does measure atmospheric pressure, but I don't have those values loaded.",
       "I can give you the air-temperature range at the rover's site instead.",
       "Shall I do that?", ("How cold is it?", "What does REMS measure?"), (MARS_FACTS,)),
    # ---- Dust --------------------------------------------------------------------------------------
    KB("dust_storm", (r"\bdust ?storms?\b", r"\bglobal dust\b"),
       "Yes: a planet-wide dust storm in 2018 was classified as global on June 20 and was the biggest since 2007.",
       "Curiosity wasn't affected because it uses a nuclear generator, while Opportunity's solar panels lost so much sunlight that "
       "its science had stopped by June 8.",
       "At Gale Crater the storm showed up on June 5 in temperature readings from a sample-funnel actuator, and the dust had "
       "settled by about September 18.",
       "Want to hear about dust devils too?", ("Are there dust devils?", "What powers Curiosity?"), (GODDARD_DUST,)),
    KB("dust_devils", (r"\bdust ?devils?\b", r"\bwhirlwinds?\b"),
       "Yes: Curiosity's Navcam filmed a dust devil in Gale Crater on sol 1597 (February 1, 2017), in the local summer afternoon.",
       "Dust devils are whirlwinds that form when sunlight warms the ground, which heats the air so it rises, the same process "
       "as on Earth.",
       "Watching them shows wind directions and how the surface and atmosphere interact.",
       "Want to hear about the 2018 global dust storm?", ("Tell me about the dust storm", "What does REMS measure?"),
       (DUST_DEVIL,)),
    # ---- Driving and terrain ---------------------------------------------------------------------
    KB("driving", (r"\bwheels?\b", r"\bpunctur", r"\bwhat makes driving (hard|difficult)\b",
                   r"\bhow (does|do) (curiosity|the rover) (drive|navigate)\b"),
       "Sharp rocks are the main danger: they can puncture the rover's aluminum wheels.",
       "Punctures and rips sped up in late 2013, so the team now drives with extra precautions, checks the wheels often and "
       "has tested things like driving backward.",
       "COSMIC TRAIL models slope only, so it can't see sharp rocks or loose sand.",
       "Want me to check the slope along your route?", ("Analyze my route", "Will my route cross the dunes?"), (JPL_DRIVE,)),
    KB("hirise", (r"\bhirise\b", r"\bhow (do|does) (nasa|scientists|mission teams?|rovers?|they|the team) (plan|choose|pick)\b.*\b(routes?|paths?)\b"),
       "HiRISE is a camera on NASA's Mars Reconnaissance Orbiter, and its images help mission teams assess the terrain.",
       "Teams compare several candidate routes with such orbital images; before landing, the Curiosity science team mapped the "
       "terrain in 140 quadrants, each about 1.5 km wide.",
       "COSMIC TRAIL builds its 5 m terrain grid from HiRISE elevation models in the same spirit.",
       "Want me to check how steep the ground is where you are?", ("How steep is it here?", "Analyze my route"),
       (JPL_DRIVE,), caveat="The 5 m grid description is from COSMIC TRAIL's own documentation."),
    # ---- More common Mars mission questions -------------------------------------------------------
    KB("mars_red", (r"\bwhy is mars red\b", r"\bwhy (does|do) mars (look|appear) red\b", r"\bred planet\b"),
       "Mars looks red because iron-bearing minerals in its dust have oxidised, much like rust on Earth.",
       "Fine dust spreads across the surface and gives the planet its familiar reddish colour.",
       "I can also explain what Mars' atmosphere is made of.",
       "Would you like to know whether humans could breathe there?", ("Can humans breathe on Mars?", "What is Mars' atmosphere made of?"), (MARS_FACTS,)),
    KB("human_breathing", (r"\b(can|could) (humans?|people|astronauts?) breathe\b.*\bmars\b", r"\bis mars air breathable\b", r"\bcan you breathe on mars\b"),
       "No — humans cannot breathe the Martian air without life-support equipment.",
       "Mars has a very thin atmosphere made mostly of carbon dioxide, not an oxygen-rich atmosphere like Earth's.",
       "A crewed mission would need a pressurised habitat and a reliable oxygen supply.",
       "Would you like to know what makes Mars' environment challenging for explorers?", ("What is Mars' atmosphere made of?", "How cold does Mars get?"), (MARS_FACTS,)),
    KB("life_on_mars", (r"\bis there (any )?life on mars\b", r"\bhas (nasa|curiosity) found life\b", r"\bdid (we|nasa|curiosity) find (any )?life\b.*\bmars\b"),
       "No confirmed evidence of life on Mars has been found.",
       "Curiosity did find that ancient conditions at Yellowknife Bay could once have supported microbial life, but habitability is not proof that life existed.",
       "I can show you why clay minerals and ancient lake deposits matter to that investigation.",
       "Would you like to hear what Curiosity discovered at Yellowknife Bay?", ("Why are clays important?", "Tell me about Yellowknife Bay"), (JPL_YK,),
       caveat="This describes the findings cited by NASA; it is not a claim that every Martian environment has been searched."),
    KB("mars_moons", (r"\bhow many moons (does|has) mars\b", r"\bwhat are mars('s| ) moons\b", r"\bphobos and deimos\b"),
       "Mars has two small moons: Phobos and Deimos.",
       "They are much smaller than Earth's Moon and orbit close to Mars.",
       "I can also tell you about the planet's day and year.",
       "Would you like to know how long a Martian day lasts?", ("What's a sol?", "How big is Mars?"), (MARS_FACTS,)),
    KB("olympus_mons", (r"\bolympus mons\b", r"\blargest volcano\b.*\bmars\b", r"\bvolcano(es)? on mars\b"),
       "Olympus Mons is the largest volcano in the Solar System.",
       "It is a giant shield volcano on Mars, far larger than any volcano on Earth.",
       "For a closer look at the terrain in this project, I can help explore Gale Crater instead.",
       "Would you like to learn about Gale Crater or Mount Sharp?", ("What is Gale Crater?", "Tell me about Mount Sharp"), (MARS_FACTS,)),
    KB("mars_seasons", (r"\bdoes mars have seasons\b", r"\bseasons on mars\b", r"\bwhy are mars seasons\b"),
       "Yes — Mars has seasons because its axis is tilted as it orbits the Sun.",
       "A Martian year lasts about 687 Earth days, so its seasons last longer than Earth's.",
       "Season and location both matter when interpreting a weather observation.",
       "Would you like to compare a Martian day with a Martian year?", ("What's a sol?", "How cold does Mars get?"), (MARS_FACTS,)),
    # ---- Things NASA's pages don't give a figure for ----------------------------------------------
    KB("no_figure", (r"\bgravity\b", r"\bsignal delay\b", r"\b(communication|radio)s? delay\b", r"\bhow long.*\bsignal\b"),
       "I don't have a NASA-sourced figure for that, so I won't guess.",
       "I only state facts from NASA pages that I have checked, and I can't look things up live.",
       "NASA's Mars facts page (science.nasa.gov/mars/facts) is a good place to check.",
       "Is there something about the terrain, minerals or weather I can help with instead?",
       ("Am I safe here?", "What minerals are nearby?", "How cold is it?"), (MARS_FACTS,)),
    # ---- About COSMIC TRAIL itself (project documentation, not NASA data) ---------------------------
    KB("how_route", (r"\bhow (do|can) i (plan|make|find|create|set)\b.*\b(routes?|paths?)\b", r"\bplan a route\b", r"\bfind route\b"),
       "Set point A and point B on the map, then press Find Route.",
       "The router avoids ground steeper than 15° and then shows the route's length, steepest slope and climb.",
       "You can also ask me for the best path to clay and tap Set as Destination B.",
       "Want me to check the route once it's planned?", ("Best path to clay?", "Analyze my route"), (DOCS,), nasa=False),
    KB("slope_limits", (r"\bwhy (15|ten|10)\b", r"\b(slope|steepness) (limit|threshold)s?\b", r"\bwhat (is|are) the (slope )?(limits?|thresholds?)\b",
                        r"\bhow steep is too steep\b"),
       "COSMIC TRAIL treats ground steeper than 15° as too steep to walk and anything over 10° as a caution.",
       "The 10° caution threshold comes from NASA's MSL Engineering User Guide, and the 15° limit from Apollo EVA traverses.",
       "These are planning thresholds from past missions, not a safety certification.",
       "Want me to check how steep it is where you are?", ("How steep is it here?", "Any hazards nearby?"), (DOCS,), nasa=False),
    KB("how_data", (r"\bwhat data\b", r"\bwhere (does|do|did) (your|the) (terrain|map|slope|elevation) (data|come)\b", r"\bdata sources?\b"),
       "My terrain answers come from a 5 m grid built from HiRISE elevation models, with USGS data filling the gaps.",
       "Minerals come from orbital detection sites and Curiosity's own results, and weather facts come from NASA's REMS material.",
       "Every answer carries a source badge and a caveat so you can see how far to trust it.",
       "Want to know what the terrain data can't show?", ("Can I trust your answers?", "What does REMS measure?"), (DOCS,), nasa=False),
    KB("limits", (r"\b(is|are) (this|you|it) (accurate|reliable|safe for astronauts|certified|trustworthy)\b", r"\blimitations?\b",
                  r"\bcan i trust\b", r"\bhow accurate\b"),
       "Treat me as a planning aid, not a safety certification.",
       "I judge terrain on slope only from a 5 m grid, so boulders, loose sand and small scarps are invisible to me.",
       "Read the caveat under each answer to see what it leaves out.",
       "Want me to check the ground around you?", ("Am I safe here?", "Any hazards nearby?"), (DOCS,), nasa=False),
    KB("are_you_ai", (r"\b(are you|is this) (an? )?(ai|chatgpt|gpt|llm|language model|real ai|human|bot)\b", r"\bhow do you work\b"),
       "I'm ARIA, a rule-based assistant, not a language model.",
       "I match your question to a topic and answer from the data loaded in COSMIC TRAIL and the NASA material I've checked, which is "
       "why I can tell you where each answer comes from.",
       "It also means I'll say \"I don't have that\" instead of guessing.",
       "What would you like to explore?", ("Am I safe here?", "What minerals are nearby?", "How cold is it?"), (DOCS,), nasa=False),
)

_COMPILED = [(e, [re.compile(p) for p in e.patterns]) for e in ENTRIES]


def lookup(message: str) -> KB | None:
    """First entry whose pattern matches the (lower-cased) message, or None."""
    m = message.lower()
    for entry, regexes in _COMPILED:
        if any(r.search(m) for r in regexes):
            return entry
    return None
