"""NASA-sourced Gale Crater weather facts for ARIA's weather answers.

Hackathon rule: ARIA may only state what NASA-provided data and documentation say. Every value and
statement below comes from one of these, and nothing here is a live reading or a loaded REMS data product:

  * NASA/JPL "Steady Temperatures at Mars' Gale Crater" (PIA16913), REMS air-temperature graph
  * The hackathon's "Mars Weather & Temperature Data Resources" guide, which summarises the
    NASA Curiosity REMS pages and the NASA PDS Atmospheres Node REMS archive (MOD RDR product)

If a REMS reduced-data (RDR) summary is added later, load it in a new module and cite the dataset,
its version and the access date. Do not add figures from outside NASA material.
"""
from __future__ import annotations

# --- Where and what -----------------------------------------------------------------------------
# Curiosity landed inside Gale Crater on 6 August 2012 at Bradbury Landing, in the Aeolis Palus area.
LANDING_SITE = "Bradbury Landing"
LANDING_DATE = "6 August 2012"

# REMS = Rover Environmental Monitoring Station, the meteorological instrument suite on Curiosity.
REMS_MEASURES = ("air temperature", "ground temperature", "atmospheric pressure",
                 "wind speed and direction", "relative humidity", "UV radiation")
REMS_ARCHIVE = "NASA PDS Atmospheres Node (REMS archive, reduced MOD RDR data)"
REMS_UNITS_NOTE = "REMS temperatures are archived in Kelvin (°C = K - 273.15)"

# --- Air temperature (REMS on Curiosity) ---------------------------------------------------------
# NASA/JPL PIA16913. Covers mid-August 2012 to late February 2013 (early mission). Air-temperature
# highs were around 0 °C and lows around -70 °C. Historical observations, not a forecast and not a
# fixed range for every Martian season.
AIR_TEMP_HIGH_C = 0
AIR_TEMP_LOW_C = -70
AIR_TEMP_PERIOD = "mid-Aug 2012 – late Feb 2013"
AIR_TEMP_SOURCE = "NASA/JPL PIA16913"
AIR_TEMP_URL = "https://science.nasa.gov/resource/steady-temperatures-at-mars-gale-crater/"

# NASA's mapping note: a REMS reading is a measurement at the rover's location at the time of
# observation. Do not apply one rover reading to every point across the crater; crater-wide maps need
# rover observations combined with suitable spatial climate or terrain models (e.g. MarsWRF, a modelled
# product rather than a direct observation).
MAPPING_NOTE = "REMS readings are taken at the rover's location, not at every point of Gale Crater."

# --- Word lists used by Assistant.weather ---------------------------------------------------------
TEMPERATURE_WORDS = ("temperature", "temperatures", "cold", "hot", "warm", "freezing", "heat", "degrees")
# word -> what ARIA calls it when no data is loaded for it
NOT_LOADED = {
    "wind": "wind", "windy": "wind",
    "pressure": "pressure",
    "humidity": "humidity", "humid": "humidity",
    "uv": "UV", "ultraviolet": "UV",
    "radiation": "radiation",
    "dust storm": "dust",
}
ABOUT_WORDS = ("rems", "instrument", "sensor", "sensors", "measure", "measures", "measured", "measuring")
CRATER_WIDE_WORDS = ("crater", "everywhere", "anywhere", "whole", "entire", "across", "layer", "map")
