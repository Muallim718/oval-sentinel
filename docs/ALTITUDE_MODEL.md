# Independent flight feedback model

[test_altitude_feedback.py](../tests/test_altitude_feedback.py) drives the actual
controller with independent 20 Hz movement feedback and 10 Hz commands. It is a
limited physics test, not the server, house AI, or a practice-score predictor.

It reads the published gravity, ground/air acceleration, speed, jump, jet thrust,
rise cap, energy drains, and delayed regeneration from the kit configuration.
Movement vectors are normalized as in the protocol. The model resolves whole-body
ceiling contact, horizontal collisions, descending roof support while the body
overlaps an edge, and approximate outward edge slide. Invariants reject free jets,
ignored jumps, passing through ceilings/walls, and center-only roof support.

Seven complete flights use three synthetic heights and four distinct public-map
roofs. Each executes one real jump, spends energy for every jet substep, lands
grounded, reaches the deep inset, and holds for at least three seconds. These
successful flights use no ceiling contacts or wall slides.

| Case | Rise | Time through three seconds of holding | Minimum energy |
| --- | ---: | ---: | ---: |
| Synthetic | 12 m | 9.6 s | 71.5 |
| Synthetic | 25 m | 10.7 s | 52.0 |
| Synthetic | 40 m | 12.4 s | 29.5 |
| Public roof | 7.25 m | 8.5 s | 79.0 |
| Public roof | 14.42 m | 9.2 s | 68.5 |
| Public roof | 18.73 m | 9.5 s | 62.5 |
| Public roof | 34.26 m | 10.6 s | 38.5 |

Separate tests check an eight-second healthy hold and a zone-triggered exit that
retains altitude ownership until actual terrain landing. Integration tests cover
stalled roof exits, pressure before launch, pressure while holding, firing masks,
body growth, pitch limits, upgrades, reloads, and passive weapon pickups.

Run the focused physics tests:

```sh
python3 -m unittest discover -s tests -p test_altitude_feedback.py -v
```

Run the full project checks, including quiet-map search timing:

```sh
python3 tools/verify.py
```

Use `py -3.13` in place of `python3` on this Windows computer.

Exact server update ordering, wall slide, eave push-out, roof-edge tolerances,
overlapping mechs, and knockback are not reproduced. Ceiling behavior is
conservative and gives no automatic eave escape. Collision and terrain use the
project's geometric approximations. Combat during ascent, enemy pursuit, moving
zones over a full match, and placement are absent. A completed flight does not
prove that taking or holding that roof is strategically safe.
