# ARIA demo questions

Questions we rehearse for the demo. Each one is checked by `tests/test_demo_questions.py` (intent detection),
so if you change ARIA's keywords, run `python -m pytest tests/test_demo_questions.py`.

- ARIA is rule-based and answers in English only.
- Slope, hazard, elevation and place questions use the **centre of the map**; move the map first.
- Route questions need a route: set A and B and press **Find Route**, then ask.
- Weather answers use **NASA material only** (REMS air-temperature graph PIA16913 and the NASA REMS/PDS descriptions), never live data.
- Replies follow **answer → why → suggestion → follow-up question**, and the chat shows tappable follow-up questions.
- "Mission knowledge" answers (below) come from `app/mars_kb.py`, written only from cited NASA pages. Where NASA's pages give no figure (e.g. gravity), ARIA says so instead of guessing.

## Is it safe to walk here?

Slope verdict (✅ / ⚠️ / ❌) from the 5 m HiRISE grid, with the steepest ground nearby. With a compass direction it checks 500 m in a straight line.

1. Am I safe here?
2. Is it safe to walk north?
3. How steep is it here?
4. Can I climb east from here?
5. What is the slope here?
6. Is this spot safe to walk on?

## Hazards

Nearest slope over 15° within 250 m and how many steep cells are around.

7. Any hazards nearby?
8. Is there anything dangerous around me?
9. Are there cliffs near here?
10. What should I avoid?

## Elevation

Height in metres relative to the Mars areoid, with data quality.

11. What is the elevation here?
12. How high am I?
13. What's the altitude?

## Distance

Great-circle distance to a named place, or the length of the planned route.

14. How far is Mount Sharp?
15. How far is Bradbury Landing?
16. What is the distance to Aeolis Palus?

## Route

Summary of the last planned route: length, max slope, climb. Press Find Route first.

17. Analyze my route
18. Is my route safe?
19. Is my path safe?
20. How long is my route?

## Path to clay

Direction, distance and terrain to Yellowknife Bay; offers a Set as Destination B button.

21. What's the best path to clay?
22. Take me to Yellowknife Bay
23. Where is the nearest clay?

## Minerals

Nearest orbital mineral detections (CRISM/OMEGA/THEMIS) and the clays Curiosity confirmed.

24. What minerals are nearby?
25. Is there any sulfate around?
26. Tell me about the geology here
27. Are there clays at Gale Crater?

## What is here?

Terrain type, elevation, geologic unit, nearest minerals, HiRISE coverage.

28. What's here?
29. Where am I?
30. Tell me about this place

## Weather (NASA REMS facts only)

Air-temperature range at Curiosity's site, what REMS measures and where its data comes from, and an honest "no data loaded" for ground temperature, pressure, wind, humidity, UV and radiation. It refuses to give one temperature for the whole crater (NASA: a rover reading is a point measurement).

31. How cold is it?
32. What's the temperature?
33. How much radiation is there?
34. What's the weather like?
35. How windy is it?
36. What does REMS measure?
37. Where does the weather data come from?
38. Is the temperature the same across the whole crater?
39. What is the ground temperature?
40. How much UV is there?
41. What's the humidity?
42. What is the air pressure?

## Dunes / thermal

Whether the route crosses dune sand (high thermal risk). Press Find Route first for the whole path.

43. Is the route hot?
44. Temperature on this path?
45. Will my route cross the dunes?

## Mission knowledge (NASA pages, no dataset needed)

Curiosity, its instruments, Gale Crater, clays, dust and Mars basics, plus how COSMIC TRAIL works.

1. What instruments does Curiosity have?
2. What does ChemCam do?
3. What does CheMin do?
4. What does SAM do?
5. What does RAD measure?
6. What powers Curiosity?
7. What is Curiosity?
8. What is Gale Crater?
9. Tell me about Mount Sharp
10. Why are clays important?
11. Was there ever water here?
12. What's a sol?
13. How cold does Mars get?
14. How big is Mars?
15. Tell me about the dust storm
16. Are there dust devils?
17. What makes driving hard for the rover?
18. How do I plan a route?
19. Why 15 degrees?
20. Can I trust your answers?
21. Are you AI?
22. How much gravity is there?

## Help

Explains what ARIA can do and gives example questions.

46. What can you do?
47. help
48. Hello
49. Who are you?

Total: 71 questions (numbering in each section is local).

## Additional Mars mission questions

These six questions exercise the expanded NASA-cited knowledge entries in `app/mars_kb.py`.

- Why is Mars red?
- Can humans breathe on Mars?
- Is there life on Mars?
- How many moons does Mars have?
- What is Olympus Mons?
- Does Mars have seasons?

Each answer gives a concise response first, a short explanation, a practical next suggestion and a follow-up question. NASA source URLs are included in the assistant response payload. ARIA remains a deterministic, rule-based assistant; this knowledge expansion is not model fine-tuning or live web retrieval.
