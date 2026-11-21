# Reactive ground-gun lab (limited model)

This is a tactical diagnostic, **not a game engine, house-bot reproduction, or
practice-score predictor**. It never uses private seeds or private endpoints.

During development, the public `game.js` asset and its explicitly referenced
`/assets/play-TzGHrICW.js` player chunk from `https://play.joinbuilders.org` were
inspected on 2026-11-21. They provide rendering/spectator code and player input
transport: the player chunk sends actions through a WebSocket and consumes server
observations. They contain no server physics or house AI. Those bundles are not
included in this repository. The lab's numbers come from the kit's public config
and protocol, not an extracted authoritative game engine.

## Run

```sh
python3 tools/ground_lab.py --project-dir . --seconds 25 --seeds 11 29 47 71
```

Run from the repository root. On Windows, replace `python3` with `py -3.13`.
Only Python's standard library is needed. Use `--output PATH` to save the JSON;
the report records source hashes and whether source files changed during the run.
It names the project folder without exposing its absolute path.

To compare against the 3.25 baseline, create a separate checkout and run the same
current tool against that checkout:

```sh
git worktree add --detach ../oval-sentinel-baseline b3dcffa
python3 tools/ground_lab.py --project-dir ../oval-sentinel-baseline --seconds 25 --seeds 11 29 47 71
```

The default suite has four scenarios and two seeds. `--scenarios` selects from
`open_pursuit`, `corner_recovery`, `crossfire_cover`, `quiet_loot`.

These scenarios use controlled flat terrain and simple walls through the real
project `World` / `Prism` collision methods. The live `Bot` receives observations
at 10 Hz and the model steps at 20 Hz. Both the player and pursuers use published
mech/gun numbers from the kit's hello config. Gun pursuers cooperate, use simple
leading aim, pursue with navigation, and do not hurt each other.

Measurements include survival to the scenario time cap, death time, HP, received
and dealt damage, regenerated HP, exposed time, shots, movement distance, collected
cubes, unsupported jump requests, and maximum bot decision time. The quiet-loot
case ends on collection, before cube stat growth or upgrade offers would need
modeling. The scenario's `alive` is held above two so the real policy does not
enter its special final-duel rule.

## What is approximated or absent

- Enemy policy is an invented deterministic pursuit model with seeded Gaussian
  gun spread. It is not an estimate of any house difficulty. Pursuers know our
  current location for navigation even behind cover, which makes this a stress
  model rather than a fair recreation of observed enemy knowledge.
  A pursuer continues navigating when a nearby wall blocks fire; it does not stop
  merely because the target is within 35 m on the other side of that wall.
- Only ground motion and the arm gun are supported. Jump/jet requests are counted
  and ignored; a controller relying on them cannot be assessed here. Secondary
  weapons, NPCs, drops, cube scaling, upgrades, effect signatures, terrain height
  variation, trees, moving zones, deaths/placements, and full match progression
  are absent. The circular static zone does deal damage outside itself.
- Aim slew is applied before firing in each substep. Exact server ordering and
  muzzle offsets are not available in the public client. Bullets begin at the
  center muzzle height, inherit no shooter velocity, and intersect the target's
  end-of-step cylinder. These choices cannot establish correctness of a subtle
  aiming change.
- Wall slide is an approximation using separate X/Y movement attempts. Body
  pushing, roof/eave physics and airborne collisions are absent. Both live Bot
  navigation and pursuer navigation come from the chosen project, so a navigation
  implementation change would also alter the modeled pursuers.
- Visibility approximates the published range, proximity, yaw wedge, line of
  sight, and five-second tracking. It ignores sounds, trees, and hearing.
- Bullets stop at cover. Damage uses gun damage, armor, and the published rear
  multiplier. Dealing and taking damage each reset the five-second heal timer.
  Gun cooldown carry preserves the published continuous held-trigger rate; the
  exact authoritative edge behavior at cooldown/reload completion remains unknown.
- The live navigator and cover planner have wall-time search caps. Route decisions
  can therefore vary with CPU load despite a fixed scenario seed. Run comparisons
  sequentially and treat the timings as approximate, not exact reproducibility or
  statistical evidence. The reported hashes identify the code used for a run.

Before every suite, assertions check cylinder intersection, blocked shots,
unobstructed front-hit damage, both combat participants' heal-timer resets, no
premature regeneration, and the 45 HP/s healing rate from config. If a future
config changes these constants, update the invariants deliberately.

## Revision 8 development comparison

One sequential 25-second comparison on 2026-11-21 used the 3.25 policy at
`b3dcffa` and the new ground-cover controller. Seeds 47 and 71 were added after
the initial 11/29 comparison. All eight wall-pressure cases lived longer in this
model; their mean death time rose from approximately 7.38 to 15.26 seconds. Every
pressure case still died before the time cap. Quiet cube collection was unchanged.
The 16 baseline scenarios took about 3.9 seconds to run, and the candidate took
about 5.2 seconds on the development machine.

| Scenario | Seed | Baseline death/collection s | Candidate death/collection s | Candidate healing HP |
| --- | ---: | ---: | ---: | ---: |
| Open pursuit | 11 | 7.55 | 7.80 | 0 |
| Open pursuit | 29 | 7.35 | 7.55 | 0 |
| Open pursuit | 47 | 7.35 | 7.55 | 0 |
| Open pursuit | 71 | 7.80 | 7.80 | 0 |
| Corner recovery | 11 | 10.40 | 15.85 | 45 |
| Corner recovery | 29 | 7.35 | 15.85 | 45 |
| Corner recovery | 47 | 7.80 | 15.85 | 45 |
| Corner recovery | 71 | 10.20 | 15.85 | 45 |
| Crossfire cover | 11 | 8.05 | 15.00 | 18 |
| Crossfire cover | 29 | 5.10 | 14.60 | 0 |
| Crossfire cover | 47 | 4.90 | 13.95 | 0 |
| Crossfire cover | 71 | 5.20 | 15.10 | 14 |
| Quiet loot | 11 | 12.35 | 12.35 | 0 |
| Quiet loot | 29 | 12.35 | 12.35 | 0 |
| Quiet loot | 47 | 12.35 | 12.35 | 0 |
| Quiet loot | 71 | 12.35 | 12.35 | 0 |

These results do **not** explain actual practice deaths or imply a score gain.
Secondary weapons and a moving zone could change the conclusion substantially.
Scored practice decides whether the new controller should be retained.

Each entity has a separate seeded spread RNG, so changing our shot count does not
change the pursuers' random-spread sequence. Seeded comparisons should still use
several scenarios: a single rollout is not strong evidence of general skill.
