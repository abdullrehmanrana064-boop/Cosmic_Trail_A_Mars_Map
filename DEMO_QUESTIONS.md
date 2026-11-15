# ARIA demo questions

Questions we rehearse for the demo. Each one is checked by `tests/test_demo_questions.py` (intent detection),
so if you change ARIA's keywords, run `python -m pytest tests/test_demo_questions.py`.

- ARIA is rule-based and answers in English only.
- Slope, hazard, elevation and place questions use the **centre of the map**; move the map first.
- Route questions need a route: set A and B and press **Find Route**, then ask.
- Weather answers are **published figures** (NASA/JPL PIA16913, Hassler et al. 2014), not live data.

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

## Weather (published figures)

Air temperature and radiation from cited studies; says honestly when wind/pressure are not loaded.

31. How cold is it?
32. What's the temperature?
33. How much radiation is there?
34. What's the weather like?
35. How windy is it?

## Dunes / thermal

Whether the route crosses dune sand (high thermal risk). Press Find Route first for the whole path.

36. Is the route hot?
37. Temperature on this path?
38. Will my route cross the dunes?

## Help

Explains what ARIA can do and gives example questions.

39. What can you do?
40. help
41. Hello
42. Who are you?

Total: 42 questions.
