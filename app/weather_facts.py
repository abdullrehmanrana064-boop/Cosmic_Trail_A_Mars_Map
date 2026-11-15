"""Published Gale Crater environment figures for ARIA's weather answers.

These are NOT live readings and NOT a REMS/RAD data product loaded into the app. Each value is a
figure published by NASA or in a peer-reviewed paper, kept here with its citation so every number
ARIA says can be traced. Add a figure only after checking it against the cited source.
"""
from __future__ import annotations

# --- Air temperature (REMS on Curiosity) -------------------------------------------------------
# NASA/JPL PIA16913 "Steady Temperatures at Mars' Gale Crater" (8 April 2013), credit
# NASA/JPL-Caltech/CAB(CSIC-INTA)/FMI/Ashima Research. Covers mid-August 2012 to late February 2013
# (about a quarter of a Mars year: late winter to the end of spring in the southern hemisphere).
# The page gives daily highs of about 0 °C (32 °F) and daily lows of about -70 °C (-94 °F).
AIR_TEMP_HIGH_C = 0
AIR_TEMP_LOW_C = -70
AIR_TEMP_PERIOD = "mid-Aug 2012 – late Feb 2013"
AIR_TEMP_SOURCE = "NASA/JPL PIA16913"
AIR_TEMP_URL = "https://www.jpl.nasa.gov/images/pia16913-steady-temperatures-at-mars-gale-crater/"

# --- Radiation (RAD on Curiosity) --------------------------------------------------------------
# Hassler et al. 2014, Science 343, 1244797 — already cited in the team's existing weather reply.
RADIATION_MSV_PER_DAY = 0.64
RADIATION_SOURCE = "Hassler et al. 2014"

# Words that mean "tell me about temperature" vs "radiation" (used by Assistant.weather).
TEMPERATURE_WORDS = ("temperature", "temperatures", "cold", "hot", "warm", "freezing", "heat", "degrees")
RADIATION_WORDS = ("radiation", "rad", "msv", "dose")
OTHER_WORDS = ("wind", "pressure", "dust storm")   # no value loaded for these
