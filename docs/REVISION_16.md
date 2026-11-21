# Revision 16: gain power before the first sustained duel

This version adds an opening phase to the 3.73 controller. During the first
55 seconds it ranks actual observed floor weapons, cubes, crates, and drones
by the time needed to gain their reward. It chooses one feasible ground route
and stops farming when a known hunter, recent hit, health, or the zone makes
the objective unsafe. An outstanding objective has until 60 seconds at most.
While no hostile target needs tracking, the torso scans at its live turn rate.

A crate or drone mission keeps the arm gun on that target until the recorded
damage confirms its defeat. The bot then walks to the observed reward. A
floor weapon is complete after the `took` receipt or the actual inventory
change. The route checks body clearance, including the final leg around a
wall. The ordinary combat and kill-salvage controllers retain priority when
the opening phase ends or combat closes in.

The controlled 20 Hz comparison keeps geometry and observations on the same
rules for both policies. Earlier gains use more sprint energy.

| Outcome | 3.73 baseline | Opening phase |
| --- | ---: | ---: |
| First sight of floor laser | 3.10 s | 0.60 s |
| Laser acquired | 11.20 s | 6.20 s |
| Laser ready to fire | 12.85 s | 7.85 s |
| First cube from the crate | 3.60 s | 2.45 s |
| Both drone cubes collected | 5.95 s | 3.05 s |

The crate result held with and without the weapon roll. Both bots used seven
gun shots for the crate and eight for the drone. The drone dealt 25 damage to
each. The new controller handed back movement and aim as soon as the pursuer
rounded the wall. This model exercises the route, pickup radius, equip delay,
retaliation, and health gain. It does not measure placement against house bots.

All 118 tests passed locally, including 16 opening-policy and four physical
feedback tests. The official checker answered 300/300 on time, with an 8.8 ms
maximum. The local crowded and growing-body maxima were 21.42 and 12.38 ms.

Commit `2b328349109577b217ef89fd1e7eba77b1aa7253` passed 118 Linux tests and
the pinned image build. The restricted container answered 300/300 on time,
with p99 13.1 ms and maximum 19.1 ms. The submitted tree was 2,344,888 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44946272646)

The practice service accepted the exact commit at 3:27 PM EST on November 21,
2026, under receipt `BB-3283154A`. It scored **3.75**, a 0.02 increase over
3.73. The site selected it as the best entry. The aggregate result cannot
show how often an early resource changed placement or whether the small
difference would persist across runs.
