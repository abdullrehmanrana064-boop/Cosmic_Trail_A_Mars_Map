"""ARIA — Astronaut Route Intelligence Assistant (rule-based, offline).

NOT a language model. Each question is matched to an intent by keywords, and the
answer is assembled from data already loaded by the backend:

  slope / elevation / hazard  → the 5 m analysis grid (HiRISE DTMs + USGS gap fill)
  outside the grid            → MOLA 463 m context heights (data/terrain_context.npz)
  route_safety / distance     → the route summary the frontend sends (last route result)
  minerals                    → bundled aqueous-mineral sites (Ehlmann & Edwards 2014)
                                + the cited science cards (app/science.py)
  weather                     → published REMS air-temperature and RAD radiation figures
                                (app/weather_facts.py, each with its citation); no live data

Replies are plain language first, numbers second (see _say):
  line 1  verdict      ✅ safe by slope / ⚠️ caution / ❌ avoid / 🔬 finding / 📍 📏 info / ❓ no data
  line 2  one plain sentence
  line 3  at most three key numbers
The source badge is drawn by the frontend from `data_source`. Verdicts compare modelled
slope against the router's thresholds (caution 10°, MSL guide; max 15°, Apollo EVA
traverses); the caveat says what the 5 m data cannot show.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .science import CARDS, mission_guide_query
from . import context as ctx
from . import weather_facts as wf

MAX_SLOPE_DEG = 15.0       # router default (Apollo EVA traverses, EPSC2024)
CAUTION_SLOPE_DEG = 10.0   # router default (NASA MSL Engineering User Guide)
TRANSECT_M = 500.0
NEIGHBOURHOOD_M = 50.0
HAZARD_RADIUS_M = 250.0
MARS_R = 3396190.0

# Intent → trigger words, in priority order (first match wins).
INTENTS: list[tuple[str, list[str]]] = [
    ("hazard", ["hazard", "hazards", "danger", "dangers", "dangerous", "avoid", "obstacle", "obstacles",
                "cliff", "cliffs"]),
    ("weather", ["weather", "temperature", "wind", "radiation", "dust storm", "pressure", "rems", "climate",
                 "cold", "hot", "warm", "freezing", "degrees"]),
    ("minerals", ["mineral", "minerals", "rock", "rocks", "geology", "clay", "sulfate", "sulphate",
                  "crism", "mudstone", "silica", "carbonate", "chloride"]),
    ("route_safety", ["route", "path", "my route", "traverse"]),
    ("distance", ["distance", "how far", "far is", "km to", "kilometres", "kilometers"]),
    ("elevation", ["elevation", "height", "altitude", "how high", "how low", "deep"]),
    ("slope", ["slope", "steep", "safe", "gradient", "incline", "walk", "climb"]),
]

DIRECTIONS = {
    "north": 0, "northeast": 45, "north-east": 45, "east": 90, "southeast": 135, "south-east": 135,
    "south": 180, "southwest": 225, "south-west": 225, "west": 270, "northwest": 315, "north-west": 315,
}

# Named places with published coordinates (science cards); matched in the message.
PLACE_WORDS = {
    "bradbury": "bradbury_landing",
    "mount sharp": "aeolis_mons", "aeolis mons": "aeolis_mons",
    "aeolis palus": "aeolis_palus",
}


@dataclass
class Answer:
    reply: str
    data_source: str
    confidence: str            # high | medium | low | none
    intent: str
    data: dict[str, Any] = field(default_factory=dict)
    caveat: str | None = None


# Location-specific questions, checked before the keyword intents ("path", "clay", "here"…).
GO_TO_CLAY = re.compile(
    r"\b(path|route|way|go|get|walk|drive|navigate|take me|head|directions?|how do i reach|best)\b.*\b(clays?|yellowknife)\b"
    r"|\b(nearest|closest)\b.*\bclays?\b")
# "Temperature on this path?", "Is the route hot?" — thermal along the ROUTE (dune sand), checked
# before the generic "weather" keywords, which would otherwise catch "temperature".
ROUTE_THERMAL = re.compile(
    r"\b(temperatures?|thermal|heat|hot|warm|cold|freezing)\b.*\b(path|route|traverse|trail|walk|way|trip)\b"
    r"|\b(path|route|traverse|trail|walk|way|trip)\b.*\b(temperatures?|thermal|heat|hot|warm|cold|freezing)\b")
PLACE_INFO = re.compile(
    r"\bwhat('?s| is) (here|this (place|spot|area))\b|\bwhere am i\b|\b(describe|tell me about) (this|here)\b"
    r"|\bwhat am i (on|standing on|looking at)\b")


def detect_intent(message: str) -> str:
    m = message.lower()
    if GO_TO_CLAY.search(m):
        return "go_to_clay"
    if PLACE_INFO.search(m):
        return "place_info"
    if ROUTE_THERMAL.search(m):
        return "route_thermal"
    for intent, words in INTENTS:
        if any(re.search(rf"\b{re.escape(w)}\b", m) for w in words):
            return intent
    return "unknown"


def detect_direction(message: str) -> tuple[str, float] | None:
    m = message.lower()
    for word in sorted(DIRECTIONS, key=len, reverse=True):   # "northeast" before "north"
        if re.search(rf"\b{re.escape(word)}\b", m):
            return word.replace("-", ""), float(DIRECTIONS[word])
    return None


def detect_place(message: str) -> dict | None:
    m = message.lower()
    for word, card_id in PLACE_WORDS.items():
        if word in m:
            card = next((c for c in CARDS if c.card_id == card_id), None)
            if card and card.lon is not None:
                return {"name": card.site, "lon": card.lon, "lat": card.lat}
    return None


def _say(verdict: str, sentence: str, numbers: list[str] | None = None, extra: str | None = None) -> str:
    """Verdict line, one plain sentence, then at most three key numbers (and an optional warning line)."""
    lines = [verdict, sentence]
    if numbers:
        lines.append(" · ".join(numbers[:3]))
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _data_quality(source: str) -> str:
    if source == "HiRISE DTM":
        return "solid HiRISE terrain data"
    if source.startswith("USGS"):
        return "USGS gap-fill data (less detailed than HiRISE)"
    return f"{source} data"


def great_circle_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_R * math.asin(math.sqrt(a))


def _fmt_pos(lon: float, lat: float) -> str:
    return f"{abs(lat):.4f}°{'S' if lat < 0 else 'N'}, {abs(lon):.4f}°{'W' if lon < 0 else 'E'}"


def _bearing_word(deg: float) -> str:
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int(((deg % 360) + 22.5) // 45) % 8]


class Assistant:
    def __init__(self, ds, context=None, minerals: dict | None = None):
        self.ds = ds               # TerrainDataset with a planetary CRS
        self.context = context     # TerrainContext (MOLA) or None
        self.minerals = minerals   # parsed data/minerals/aqueous_minerals.json or None

    # ---------- grid helpers ----------
    def _rc(self, lon: float, lat: float) -> tuple[int, int] | None:
        x, y = self.ds.proj.forward(lon, lat)
        return self.ds.grid.rc(x, y)

    def _source(self, r: int, c: int) -> str:
        if self.ds.usgs_filled is not None and self.ds.usgs_filled[r, c]:
            return "USGS Gale DEM (gap fill)"
        if self.ds.mola_filled is not None and self.ds.mola_filled[r, c]:
            return "MOLA 463 m (gap fill)"
        return "HiRISE DTM"

    def _window(self, r: int, c: int, radius_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = max(1, int(radius_m / self.ds.grid.cell))
        r0, r1 = max(0, r - n), min(self.ds.grid.height, r + n + 1)
        c0, c1 = max(0, c - n), min(self.ds.grid.width, c + n + 1)
        rr, cc = np.mgrid[r0:r1, c0:c1]
        inside = np.hypot(rr - r, cc - c) * self.ds.grid.cell <= radius_m
        return self.ds.slope[r0:r1, c0:c1], inside, np.stack([rr, cc])

    def _outside(self, lon: float, lat: float, what: str) -> Answer:
        verdict = "⚠️ Outside the detailed map."
        sentence = (f"This point is outside the 5 m routing grid, so I can't give {what} here — move the map "
                    "inside the dashed outline or name a place like Bradbury Landing.")
        if self.context is not None:
            h = float(self.context.sample(np.array([lon]), np.array([lat]))[0])
            return Answer(_say(verdict, sentence, [f"Rough elevation {h:,.0f} m (MOLA, 463 m — too coarse for walking)"]),
                          "MOLA 463 m", "low", "outside_grid", {"elevation_m": round(h, 1)},
                          caveat=f"Position: {_fmt_pos(lon, lat)}.")
        return Answer(_say(verdict, sentence), "none", "none", "outside_grid", caveat=f"Position: {_fmt_pos(lon, lat)}.")

    # ---------- intents ----------
    def slope(self, lon: float, lat: float, message: str) -> Answer:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "slopes")
        direction = detect_direction(message)
        if direction:
            return self._transect(lon, lat, *direction)
        r, c = rc
        s, inside, _ = self._window(r, c, NEIGHBOURHOOD_M)
        vals = s[inside & np.isfinite(s)]
        here = float(self.ds.slope[r, c])
        if not vals.size or not math.isfinite(here):
            return Answer(_say("❓ Can't tell here.", "This spot is on the edge of the terrain grid, where slope can't be computed."),
                          self._source(r, c), "low", "slope")
        above_c = int((vals > CAUTION_SLOPE_DEG).sum())
        above_m = int((vals > MAX_SLOPE_DEG).sum())
        src = self._source(r, c)
        if here > MAX_SLOPE_DEG:
            verdict, sentence = "❌ Avoid — this spot is too steep.", "The ground here is steeper than the 15° walking limit."
        elif above_m:
            verdict = "⚠️ Caution — steep ground right next to you."
            sentence = f"This spot is fine, but some ground within {NEIGHBOURHOOD_M:.0f} m is steeper than the 15° limit."
        elif here > CAUTION_SLOPE_DEG or above_c:
            verdict = "⚠️ Caution — moderately steep."
            sentence = f"Walkable, but parts of the ground within {NEIGHBOURHOOD_M:.0f} m are steeper than 10°."
        else:
            verdict, sentence = "✅ Yes, this spot is safe.", f"Gentle slope, {_data_quality(src)}."
        # Location context: nearest slope over the limit, and the dune map.
        hs, hin, hidx = self._window(r, c, HAZARD_RADIUS_M)
        steep = hin & np.isfinite(hs) & (hs > MAX_SLOPE_DEG)
        nearest_steep = None
        if steep.any():
            rr, cc = hidx[0][steep], hidx[1][steep]
            dd = np.hypot(rr - r, cc - c) * self.ds.grid.cell
            k = int(np.argmin(dd))
            brg = math.degrees(math.atan2(cc[k] - c, -(rr[k] - r))) % 360
            nearest_steep = {"distance_m": round(float(dd[k])), "bearing": _bearing_word(brg)}
        dune = ctx.dune_status(lon, lat)
        if dune.get("inside") and verdict.startswith("✅"):
            verdict, sentence = "⚠️ Caution — dune sand.", f"Gentle slope, but this is loose dune sand; {_data_quality(src)}."
        steep_txt = (f"nearest >15° slope {nearest_steep['distance_m']} m {ctx.short_bearing(nearest_steep['bearing'])}"
                     if nearest_steep else f"no >15° slope within {HAZARD_RADIUS_M:.0f} m")
        reply = _say(verdict, sentence,
                     [f"Slope here {here:.1f}°", f"steepest within {NEIGHBOURHOOD_M:.0f} m {vals.max():.1f}°", "limit 15°"],
                     f"{steep_txt} · {ctx.dune_line(dune)}")
        return Answer(reply, src, "high" if src == "HiRISE DTM" else "medium", "slope",
                      {"slope_deg": round(here, 2), "mean_deg": round(float(vals.mean()), 2),
                       "max_deg": round(float(vals.max()), 2), "cells_above_caution": above_c, "cells_above_max": above_m,
                       "nearest_steep": nearest_steep, "dunes": dune, "data_quality": ctx.source_at(self.ds, r, c)},
                      caveat=f"{_fmt_pos(lon, lat)}. Judged on slope only, from a 5 m grid: boulders, loose sand and "
                             "small scarps are not resolved. Thresholds come from past missions — not a safety certification.")

    def _transect(self, lon: float, lat: float, word: str, bearing: float) -> Answer:
        x0, y0 = self.ds.proj.forward(lon, lat)
        b = math.radians(bearing)
        step = self.ds.grid.cell
        slopes, elevs, sources, dist = [], [], set(), 0.0
        for i in range(int(TRANSECT_M / step) + 1):
            d = i * step
            rc = self.ds.grid.rc(x0 + d * math.sin(b), y0 + d * math.cos(b))
            if rc is None:
                break
            r, c = rc
            if math.isfinite(self.ds.slope[r, c]):
                slopes.append(float(self.ds.slope[r, c]))
            if math.isfinite(self.ds.elev[r, c]):
                elevs.append(float(self.ds.elev[r, c]))
            sources.add(self._source(r, c))
            dist = d
        if len(slopes) < 2:
            return Answer(_say("⚠️ Edge of the map.", f"Going {word} from here leaves the routing grid almost immediately."),
                          "none", "low", "slope")
        arr = np.array(slopes)
        dh = elevs[-1] - elevs[0] if len(elevs) > 1 else 0.0
        above_c, above_m = int((arr > CAUTION_SLOPE_DEG).sum()), int((arr > MAX_SLOPE_DEG).sum())
        short = dist < TRANSECT_M - step
        trend = f"rises {dh:.0f} m" if dh > 0.5 else (f"drops {-dh:.0f} m" if dh < -0.5 else "stays level")
        if above_m:
            verdict = f"❌ Avoid walking straight {word}."
            sentence = f"The ground {trend}, and the line crosses slopes steeper than the 15° limit."
        elif above_c:
            verdict = f"⚠️ Caution heading {word}."
            sentence = f"Walkable, but the ground {trend} with a few moderately steep (10–15°) patches."
        else:
            verdict = f"✅ Clear to walk {word}."
            sentence = f"Gentle ground the whole way — it {trend}."
        reply = _say(verdict, sentence,
                     [f"{dist:.0f} m checked{' (map edge)' if short else ''}", f"steepest {arr.max():.1f}°",
                      f"average {arr.mean():.1f}°"])
        return Answer(reply, " + ".join(sorted(sources)), "high" if sources == {"HiRISE DTM"} else "medium", "slope",
                      {"direction": word, "length_m": round(dist), "mean_deg": round(float(arr.mean()), 2),
                       "max_deg": round(float(arr.max()), 2), "elevation_change_m": round(dh, 1),
                       "cells_above_caution": above_c, "cells_above_max": above_m},
                      caveat=f"From {_fmt_pos(lon, lat)}. A straight line, not a planned route — use Find Route for a "
                             "path that avoids steep cells. 5 m grid; thresholds from past missions, not a safety certification.")

    def elevation(self, lon: float, lat: float, message: str) -> Answer:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "a 5 m elevation")
        r, c = rc
        e = float(self.ds.elev[r, c])
        if not math.isfinite(e):
            return Answer(_say("❓ No elevation data here.", "This cell has no height value."),
                          self._source(r, c), "none", "elevation")
        src = self._source(r, c)
        where = "below" if e < 0 else "above"
        reply = _say(f"📍 About {abs(e) / 1000:.1f} km {where} Mars \"sea level\".",
                     "That's normal for the floor of Gale Crater, one of the lowest places near the equator.",
                     [f"Elevation {e:,.0f} m (relative to the areoid)", f"from {_data_quality(src)}"])
        return Answer(reply, src, "high" if src == "HiRISE DTM" else "medium", "elevation", {"elevation_m": round(e, 2)},
                      caveat="USGS gap-fill heights were adjusted to meet the HiRISE tiles (see SCIENTIFIC_LIMITATIONS.md)."
                      if src != "HiRISE DTM" else None)

    def hazard(self, lon: float, lat: float, message: str) -> Answer:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "a hazard check")
        r, c = rc
        s, inside, idx = self._window(r, c, HAZARD_RADIUS_M)
        steep = inside & np.isfinite(s) & (s > MAX_SLOPE_DEG)
        n_steep = int(steep.sum())
        n_caution = int((inside & np.isfinite(s) & (s > CAUTION_SLOPE_DEG)).sum())
        data = {"radius_m": HAZARD_RADIUS_M, "cells_above_max": n_steep, "cells_above_caution": n_caution}
        if n_steep == 0:
            if n_caution:
                reply = _say("✅ No major hazards nearby.",
                             f"Nothing within {HAZARD_RADIUS_M:.0f} m is too steep to walk, though a few patches are moderately steep.",
                             [f"{n_caution} patches at 10–15°", "none over the 15° limit"])
            else:
                reply = _say("✅ No hazards nearby.", f"All the ground within {HAZARD_RADIUS_M:.0f} m is gentle.",
                             ["nothing over 10°"])
        else:
            rr, cc = idx[0][steep], idx[1][steep]
            d = np.hypot(rr - r, cc - c) * self.ds.grid.cell
            k = int(np.argmin(d))
            brg = math.degrees(math.atan2(cc[k] - c, -(rr[k] - r))) % 360
            here = float(self.ds.slope[r, c])
            on_steep = math.isfinite(here) and here > MAX_SLOPE_DEG
            data.update(nearest_steep_m=round(float(d[k])), nearest_steep_bearing=None if on_steep else _bearing_word(brg),
                        max_deg=round(float(s[steep].max()), 1), on_steep_cell=on_steep)
            if on_steep:
                reply = _say("❌ You're on steep ground.",
                             f"This spot is {here:.0f}°, over the 15° limit — routes start from the nearest flatter ground.",
                             [f"up to {s[steep].max():.0f}° nearby", f"{n_steep} steep cells within {HAZARD_RADIUS_M:.0f} m"])
            else:
                reply = _say("⚠️ Steep ground nearby.",
                             f"The closest slope over 15° is about {d[k]:.0f} m to the {_bearing_word(brg)}; "
                             "planned routes go around it.",
                             [f"up to {s[steep].max():.0f}°", f"{n_steep} steep cells within {HAZARD_RADIUS_M:.0f} m"])
        return Answer(reply, self._source(r, c), "high" if self._source(r, c) == "HiRISE DTM" else "medium", "hazard", data,
                      caveat=f"{_fmt_pos(lon, lat)}. Only slope is modelled (5 m grid): loose sand, small rocks "
                             "and dust are not in this data.")

    def route_safety(self, lon: float, lat: float, message: str, route: dict | None) -> Answer:
        if not route:
            return Answer(_say("❓ No route yet.", "Set A and B and press Find Route, then ask me again."),
                          "none", "none", "route_safety")
        caution = route.get("cells_above_caution") or 0
        segments = route.get("caution_segments")      # sent by the frontend (optional)
        where = route.get("caution_where")            # 'start' | 'middle' | 'end' (optional)
        smax, smean = route.get("slope_max_deg"), route.get("slope_mean_deg")
        length = route.get("surface_length_3d_m") or route.get("planimetric_length_m")
        gain = route.get("elevation_gain_m")
        feel = "mostly flat" if (smean or 0) < 3 else ("gently rolling" if (smean or 0) < 6 else "hilly")
        near = f" near the {where}" if where in ("start", "middle", "end") else ""
        sentence = (f"The path is {feel}, with some steeper stretches{near}." if caution else
                    f"The path is {feel} with no steep stretches.")
        numbers = []
        if length:
            numbers.append(f"{length / 1000:.2f} km")
        if smax is not None:
            numbers.append(f"max slope {smax:.1f}° — within the 15° EVA limit")
        if gain is not None:
            numbers.append(f"climb +{gain:.0f} m")
        extra = None
        if caution:
            n_seg = f"{segments} steep segment{'s' if segments != 1 else ''}" if segments else f"{caution} steep cells"
            extra = f"⚠️ Caution: {n_seg} (10–15°){near}."
        # The router never crosses cells over 15°, so a computed route is within the EVA limit.
        reply = _say("✅ Generally safe.", sentence, numbers, extra)
        cov = route.get("data_coverage_on_route")
        return Answer(reply, "Route result (HiRISE + USGS grid)", "high", "route_safety",
                      {k: route.get(k) for k in ("mode", "cells", "slope_max_deg", "slope_mean_deg",
                                                  "cells_above_caution", "surface_length_3d_m",
                                                  "elevation_gain_m", "elevation_loss_m", "data_coverage_on_route")},
                      caveat="Judged on slope from a 5 m grid; the router never crosses ground over 15°. "
                             "Not a statement about operational safety."
                      + (f" Data coverage on route: {cov * 100:.0f}%." if isinstance(cov, (int, float)) else ""))

    def distance(self, lon: float, lat: float, message: str, route: dict | None) -> Answer:
        place = detect_place(message)
        if place and (abs(place["lon"] - lon) > 1e-4 or abs(place["lat"] - lat) > 1e-4):
            d = great_circle_m(lon, lat, place["lon"], place["lat"])
            return Answer(_say(f"📏 {place['name']} is {d / 1000:.1f} km away.",
                               "That's a straight line — a walkable route will be longer.",
                               [f"{d / 1000:.2f} km great-circle distance"]),
                          "Science card coordinates", "high", "distance", {"distance_m": round(d), "to": place["name"]})
        if route and route.get("surface_length_3d_m"):
            L = route["surface_length_3d_m"]
            return Answer(_say(f"📏 Your route is {L / 1000:.2f} km.", "Measured along the ground, including ups and downs.",
                               [f"{(route.get('planimetric_length_m') or L) / 1000:.2f} km on the flat map"]),
                          "Route result (HiRISE + USGS grid)", "high", "distance", {"distance_m": L})
        return Answer(_say("❓ Distance to where?", "Name a place (e.g. 'How far is Mount Sharp?') or compute a route first."),
                      "none", "none", "distance")

    def minerals_near(self, lon: float, lat: float, message: str) -> Answer:
        data = {}
        pts = (self.minerals or {}).get("points") or []
        confirmed = ("Closest confirmed site: Yellowknife Bay (~0.5 km NE of Bradbury Landing) — "
                     "smectite clays confirmed by Curiosity drilling.")
        numbers = None
        if pts:
            labels = {l["class"]: l["label"] for l in self.minerals.get("legend", [])}
            ds_ = sorted(((great_circle_m(lon, lat, p["lon"], p["lat"]), p) for p in pts), key=lambda t: t[0])
            within = [(d, p) for d, p in ds_ if d <= 150_000]
            near = ds_[:3]
            d0, p0 = near[0]
            brg = _bearing_word(math.degrees(math.atan2(p0["lon"] - lon, p0["lat"] - lat)))
            verdict = f"🔬 {labels.get(p0['c'], p0['c'])} detected ~{d0 / 1000:.0f} km {brg} (orbital data)."
            numbers = [f"{len(within)} detection sites within 150 km"]
            data["nearest_sites"] = [{"class": p["c"], "distance_km": round(d / 1000, 1), "lon": p["lon"], "lat": p["lat"]}
                                     for d, p in near]
        else:
            verdict = "🔬 Clay minerals confirmed nearby by Curiosity."
        cards = {c.card_id: c for c in CARDS}
        data["cards"] = [cid for cid in ("bradbury_landing", "yellowknife_bay", "aeolis_mons") if cid in cards]
        return Answer(_say(verdict, confirmed, numbers),
                      "CRISM/OMEGA/THEMIS sites (Ehlmann & Edwards 2014) + Curiosity results" if pts else "Curiosity results (science cards)",
                      "medium", "minerals", data,
                      caveat="Orbital detection sites are points (±~0.01°), not a mineral map (Ehlmann & Edwards 2014). "
                             "Yellowknife Bay: Grotzinger et al. 2014; Vaniman et al. 2014. "
                             "Habitability does not mean life was present.")

    def place_info(self, lon: float, lat: float, message: str) -> Answer:
        """'What's here?': terrain type, elevation, geologic unit, nearest minerals, data coverage."""
        rc = self._rc(lon, lat)
        unit = ctx.geologic_unit(lon, lat)
        orb = ctx.nearest_orbital_mineral(lon, lat, self.minerals)
        clay = ctx.nearest_confirmed_clay(lon, lat)
        data: dict[str, Any] = {"geologic_unit": unit, "nearest_orbital_mineral": orb,
                                "nearest_confirmed_clay": {k: clay[k] for k in ("name", "distance_m", "bearing")}}
        unit_txt = (f"{unit['unit']} unit ({unit['age_word']}, approx. map)" if unit
                    else "outside the mapped geologic units")
        clay_txt = (f"{clay['name']} clays {clay['distance_m'] / 1000:.1f} km {ctx.short_bearing(clay['bearing'])}"
                    if clay["distance_m"] >= 50 else f"you're at {clay['name']} (clays confirmed)")
        orb_txt = (f"{orb['label'].split(' (')[0]} (orbital) {orb['distance_m'] / 1000:.0f} km "
                   f"{ctx.short_bearing(orb['bearing'])}" if orb else None)
        if rc is None:
            data["hirise_coverage"] = False
            verdict = "📍 Outside the detailed 5 m map."
            sentence = f"Geology: {unit_txt}. Only coarse MOLA heights here — HiRISE coverage ❌."
            return Answer(_say(verdict, sentence, [t for t in (clay_txt, orb_txt) if t]),
                          "MOLA 463 m + science cards", "low", "place_info", data,
                          caveat=f"{_fmt_pos(lon, lat)}. Unit polygons are simplified rectangles from USGS SIM 3292.")
        r, c = rc
        e = float(self.ds.elev[r, c])
        s_, inside, _ = self._window(r, c, NEIGHBOURHOOD_M)
        vals = s_[inside & np.isfinite(s_)]
        src = self._source(r, c)
        hirise = src == "HiRISE DTM"
        dune = ctx.dune_status(lon, lat)
        kind = "Dune sand" if dune.get("inside") else ctx.terrain_word(float(vals.mean()) if vals.size else 0.0)
        data.update(elevation_m=round(e, 1), terrain=kind, hirise_coverage=hirise, data_source=src, dunes=dune)
        verdict = f"📍 {kind}, {e:,.0f} m."
        sentence = f"{unit_txt}; {clay_txt}."
        numbers = [t for t in (orb_txt, f"HiRISE coverage {'✅' if hirise else '❌ (USGS gap fill)'}") if t]
        return Answer(_say(verdict, sentence, numbers), f"{src} + CRISM/OMEGA/THEMIS sites + USGS SIM 3292",
                      "high" if hirise else "medium", "place_info", data,
                      caveat=f"{_fmt_pos(lon, lat)}. Elevation relative to the Mars areoid. Geologic unit from simplified "
                             "SIM 3292 rectangles (1:20M map). Terrain type from slope only.")

    def go_to_clay(self, lon: float, lat: float, message: str) -> Answer:
        """'Best path to clay?': direction, distance and terrain to the nearest confirmed clay site."""
        site = ctx.nearest_confirmed_clay(lon, lat)
        action = {"type": "set_destination", "lon": site["lon"], "lat": site["lat"], "label": site["name"]}
        data: dict[str, Any] = {"target": {k: site[k] for k in ("name", "lon", "lat", "distance_m", "bearing")},
                                "action": action}
        if site["distance_m"] < 50:
            return Answer(_say(f"🔬 You're at {site['name']}.",
                               f"Curiosity confirmed {site['mineral']} here ({site['how']})."),
                          "Science cards", "medium", "go_to_clay", data, caveat=f"Source: {site['source']}.")
        km = site["distance_m"] / 1000
        prof = ctx.line_profile(self.ds, lon, lat, site["lon"], site["lat"]) if self.ds.proj else {"sampled": 0}
        data["terrain_between"] = prof
        if not prof.get("sampled"):
            terrain = "The terrain in between is outside the 5 m map, so I can't check it."
        else:
            feel = ctx.terrain_word(prof["mean_deg"]).replace("Flat plain", "Mostly flat terrain")
            n = prof["steep_sections"]
            if n == 0:
                terrain = f"{feel}, no steep sections on the straight line."
            elif n == 1:
                terrain = f"{feel}, one steep section ({prof['max_deg']:.0f}°) {ctx.where_word(prof['steepest_at'])}."
            else:
                terrain = (f"{feel}, {n} steep sections — steepest {prof['max_deg']:.0f}° "
                           f"{ctx.where_word(prof['steepest_at'])}.")
            if prof["covered_fraction"] < 0.95:
                terrain += f" (Only {prof['covered_fraction'] * 100:.0f}% of the line is inside the 5 m map.)"
        reply = _say(f"🧭 {site['name']} is {km:.1f} km {ctx.short_bearing(site['bearing'])}.", terrain,
                     [f"{site['mineral']} confirmed by Curiosity", _fmt_pos(site["lon"], site["lat"])],
                     "Recommended route: tap “Set as Destination B”, then Find Route.")
        return Answer(reply, "Science cards + HiRISE DTM (line check)", "medium", "go_to_clay", data,
                      caveat=f"Straight-line check from {_fmt_pos(lon, lat)}, not a planned route. "
                             f"{site['name']} position is approximate; source: {site['source']}.")

    def route_thermal(self, lon: float, lat: float, message: str, route: dict | None) -> Answer:
        """Thermal risk along the planned route: does it cross dune sand (data/hazard_zones.geojson)?"""
        notes = ctx.dune_notes()
        note = notes[0]["note"] if notes else None
        srcs = "; ".join(sorted({s for n in notes for s in (n.get("temperature_source"), n.get("source")) if s}))
        caveat = ("Dune outline is approximate. Temperatures are published REMS statistics"
                  + (f" ({srcs})" if srcs else "") + ", not live data — no weather is loaded.")
        source = "Route context (hazard_zones.geojson) + published REMS statistics"
        thermal = (route or {}).get("thermal")
        if not route:
            # No route yet: answer for the spot at the map centre, and ask for a route.
            st = ctx.dune_status(lon, lat)
            if not st["loaded"]:
                return Answer(_say("❓ Dune map not loaded.", "I can't check dune sand, so I can't judge thermal risk."),
                              "none", "none", "route_thermal")
            verdict = (f"⚠️ This spot is on {st['name']} sand — HIGH thermal risk." if st["inside"] else
                       f"✅ This spot is off the dunes ({st['distance_m'] / 1000:.1f} km from {st['name']}).")
            return Answer(_say(verdict, note or "Dark dune sand heats and cools more than rocky ground.",
                               extra="No route yet — press Find Route, then ask again to check the whole path."),
                          source, "medium", "route_thermal", {"dunes": st, "note": note}, caveat=caveat)
        if not thermal:
            return Answer(_say("❓ No thermal check for this route.",
                               "Re-run Find Route so the dune-crossing check is included, then ask again."),
                          "none", "none", "route_thermal")
        if not thermal.get("checked"):
            return Answer(_say("❓ Dune map not loaded.", "Dune crossings on this route weren't checked."),
                          "none", "none", "route_thermal", {"thermal": thermal})
        if thermal.get("crossings"):
            names = ", ".join(thermal.get("dunes") or ["dune sand"])
            frac = thermal.get("fraction")
            share = f" (~{frac * 100:.0f}% of the route)" if isinstance(frac, (int, float)) else ""
            return Answer(_say(f"⚠️ HIGH thermal risk — this path crosses {names}{share}.",
                               note or "Dark dune sand heats and cools more than rocky ground.",
                               extra="Plan the dune crossing for the morning, or move A/B to route around the sand."),
                          source, "medium", "route_thermal", {"thermal": thermal, "note": note}, caveat=caveat)
        return Answer(_say("✅ LOW thermal risk — this path stays off the dunes.",
                           f"No dune crossings. For reference: {note}" if note else "No dune crossings."),
                      source, "medium", "route_thermal", {"thermal": thermal, "note": note}, caveat=caveat)

    def weather(self, lon: float, lat: float, message: str) -> Answer:
        """Published Gale Crater temperature / radiation figures (app/weather_facts.py). Never live data."""
        m = message.lower()
        has = lambda words: any(re.search(rf"\b{re.escape(w)}\b", m) for w in words)
        asks_temp, asks_rad = has(wf.TEMPERATURE_WORDS), has(wf.RADIATION_WORDS)
        asks_general = has(("weather", "climate", "rems"))
        if has(wf.OTHER_WORDS) and not (asks_temp or asks_rad or asks_general):
            # Wind / pressure / dust: nothing verified is loaded, so say so.
            return Answer(_say("❓ No wind or pressure data loaded.",
                               "COSMIC TRAIL has no REMS wind, pressure or dust readings, so I can't give a value.",
                               [f"Published: radiation ≈ {wf.RADIATION_MSV_PER_DAY} mSv/day at Gale ({wf.RADIATION_SOURCE})"]),
                          "Published study (no live data)", "none", "weather",
                          caveat="Not live data. Do not use for planning.")
        temp_numbers = [f"typical daily high ≈ {wf.AIR_TEMP_HIGH_C} °C", f"typical daily low ≈ {wf.AIR_TEMP_LOW_C} °C"]
        rad_number = f"radiation ≈ {wf.RADIATION_MSV_PER_DAY} mSv/day ({wf.RADIATION_SOURCE})"
        rad_only = asks_rad and not (asks_temp or asks_general)
        if rad_only:
            reply = _say("☢️ Radiation at Gale is about 0.64 mSv per day.",
                         "That is the dose Curiosity's RAD instrument measured on the surface.", [rad_number])
            source, conf = f"Published study ({wf.RADIATION_SOURCE}, RAD on Curiosity)", "medium"
        else:
            swing = wf.AIR_TEMP_HIGH_C - wf.AIR_TEMP_LOW_C
            with_rad = asks_rad or asks_general
            numbers = temp_numbers + ([rad_number] if with_rad else [])
            reply = _say("🌡️ Very cold at Gale Crater.",
                         f"Air temperature swings by roughly {swing} °C between a typical day's high and low "
                         f"({wf.AIR_TEMP_PERIOD}).", numbers)
            source = f"Published REMS summary ({wf.AIR_TEMP_SOURCE})" + (f" + {wf.RADIATION_SOURCE} (RAD)" if with_rad else "")
            conf = "medium"
        caveat = ("Published figure, not live data. Radiation varies with solar activity and season. "
                  "Do not use for planning." if rad_only else
                  f"Published figures for {wf.AIR_TEMP_PERIOD}, not live weather and not a forecast. "
                  "Ground temperature differs from air temperature and changes with season and place. "
                  "Do not use for planning.")
        return Answer(reply, source, conf, "weather",
                      {"air_temp_high_c": wf.AIR_TEMP_HIGH_C, "air_temp_low_c": wf.AIR_TEMP_LOW_C,
                       "period": wf.AIR_TEMP_PERIOD, "radiation_msv_per_day": wf.RADIATION_MSV_PER_DAY,
                       "source_url": wf.AIR_TEMP_URL},
                      caveat=caveat)

    def unknown(self, lon: float, lat: float, message: str) -> Answer:
        g = mission_guide_query(message)
        if g.get("matched_cards"):
            return Answer("📚 " + g["response"], "Science cards (Mission Guide)", "medium", "guide",
                          {"cards": [c["card_id"] for c in g["matched_cards"]]})
        return Answer(_say("❓ I didn't catch that.",
                           "Ask me about slopes, hazards, what's here, the way to clay, your route or minerals.",
                           ["Try: 'Am I safe here?'", "'Is it safe to walk north?'"]), "none", "none", "unknown")

    # ---------- entry point ----------
    def answer(self, message: str, lon: float, lat: float, route: dict | None = None) -> dict:
        place = detect_place(message)
        intent = detect_intent(message)
        # "...from Bradbury Landing" → analyse there (not for distance questions, which need both ends).
        if place and intent not in ("distance", "route_safety", "go_to_clay", "route_thermal"):
            lon, lat = place["lon"], place["lat"]
        handler = {
            "slope": lambda: self.slope(lon, lat, message),
            "elevation": lambda: self.elevation(lon, lat, message),
            "hazard": lambda: self.hazard(lon, lat, message),
            "route_safety": lambda: self.route_safety(lon, lat, message, route),
            "distance": lambda: self.distance(lon, lat, message, route),
            "minerals": lambda: self.minerals_near(lon, lat, message),
            "weather": lambda: self.weather(lon, lat, message),
            "place_info": lambda: self.place_info(lon, lat, message),
            "go_to_clay": lambda: self.go_to_clay(lon, lat, message),
            "route_thermal": lambda: self.route_thermal(lon, lat, message, route),
        }.get(intent, lambda: self.unknown(lon, lat, message))
        a = handler()
        return {"reply": a.reply, "data_source": a.data_source, "confidence": a.confidence,
                "intent": a.intent, "location": {"lon": lon, "lat": lat}, "data": a.data, "caveat": a.caveat,
                "engine": "rule-based (no language model, offline)"}
