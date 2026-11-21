# Revision 8: make cover a behavior, not just a destination

Baseline: revision 7, **3.25** placement points. This is a substantial redesign of
ground positioning and local motion, built on the best scored combat policy.

**Scored result: 3.63**, up 0.38 displayed points from 3.25. The controller is
retained and selected as the best entry. This is useful progress, while the
observed board position of 156 remains below the leading teams.

## The structural failure

The previous strategic goal scorer rewarded positions behind walls, but local
steering ignored those walls when repelling from remembered enemies. It kept
orbiting whenever an enemy was nearby, even while safely hidden at its intended
destination. A safe goal therefore did not produce a sustained safe position.

An independent 20 Hz motion probe gave the old controller an ideal stationary
cover goal. It issued no stop commands, traveled approximately 136 m over ten
seconds, and drifted roughly 31 m from that goal. The replacement holds the same
protected position for ten seconds without drift or boost use. These are
controlled geometric/acceleration tests, not game matches.

## One coherent replacement

`sentinel/cover.py` turns public building geometry into ground shelter anchors.
It checks live body dimensions, zone safety, incoming torso/head/flank firing
lanes, and the approach. It commits to a useful shelter, holds actual protection,
and looks for more protected separation when a pursuer comes close. A fifth
exposed enemy vetoes holding even though candidate search is bounded to four.

`sentinel/movement.py` replaces perpetual orbiting with nine bounded horizontal
command rollouts, including braking. Forecasts integrate current velocity and
published acceleration in 50 ms steps. Exposing a previously hidden body is
expensive; repulsion is applied to visible firing lanes rather than through
solid walls. Exposed healthy duels retain evasive motion. Projectile hazards,
weapon charging slowdown, live body clearance, and the predicted zone contribute
to the choice. The 0.75 s terminal point is a heuristic; only the nearer 0.4 s
path is collision-checked.

The main decision loop now keeps these layers consistent:

- Recovery and crossfire can take a committed ground shelter goal.
- Safe recovery suppresses optional shots, including weak-target finishes and
  over-wall mortars that would restart the healing delay. Releasing an existing
  laser charge can still fire it into the intervening cover.
- A ground shelter cancels stale jet intent. Failed approaches are rejected
  temporarily, including a route that returns a nearby waypoint without making
  physical progress toward the distant shelter.
- New firing lanes, body growth, and zone movement revalidate protection. Cover
  uses the same adaptive rotation look-ahead as ordinary goal planning.

There is no roof-flight controller, weapon preference experiment, hidden map
knowledge, private seed inference, trained model, or new runtime dependency.
The 3.25 gun-return-fire policy and ordinary weapon aiming remain the baseline.

## Validation

All **80 behavioral tests** pass locally. This includes the previous 48 tests,
20 shelter tests, and 12 motion/integration tests. Independent movement feedback
tests exercise high-speed corner braking, projectile evasion, exposed duels,
quiet route progress, and ten-second cover holding. Integration tests cover
healing despite a weak target, valid mortar arcs, stale jets, flanks, zone changes,
and distant blocked goals with misleading nearby route waypoints.

Local official checker: **300/300 on-time answers**, zero malformed, stale, or
wrong-tick replies; maximum 8.7 ms. Synthetic crowded-input and growing-body
benchmarks peaked at 11.55 and 11.82 ms on this Windows computer. These times are
observations, not a runtime guarantee on every machine.

The new [reactive ground lab](GROUND_LAB.md) drives the real bot against invented
gun pursuers using limited published-rule physics. It is a stress diagnostic,
not the server engine or house AI, and cannot predict placement. It helped find
a real corner defect: center-only cover rays missed the mech's exposed cylinder
flank. The planner and steering now share silhouette checks.

The public browser bundles contain rendering and WebSocket action transport,
not an offline authoritative simulator. The lab's earlier apparent full-healing
result was traced to an opponent-model bug (pursuers stopped behind walls),
discarded, and corrected before making comparisons. All model limitations remain
explicit in its documentation.

## Linux validation and scored practice

Commit `9bf75d70a8d209a1dd8ea4f67415ee93a9cbf7f0` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44924563407):
all 80 tests, pinned image build, and 300/300 on-time restricted-container checker
responses; p99 5.8 ms, maximum 14.0 ms. Linux host synthetic crowded and growing-body
benchmarks peaked at 16.74 and 26.83 ms, with no decision above 50 ms. The committed
tree was 2,218,632 bytes, below 20 MB.

The final corrected reactive-lab comparison improved all eight wall-pressure
cases, with modeled mean death time approximately 7.38 to 15.26 s. All pressure
cases still died before 25 s; quiet cube collection remained 12.35 s. See the
[complete case table and limitations](GROUND_LAB.md). The real scored run decides
whether to adopt this controller.

Receipt `BB-1461B1AF` was submitted at 11:27 AM EST on 2026-11-21. The previous
entry scored **3.63** and replaced 3.25 as the selected best. The implied average
placement is approximately 12.37. The observed board position was 156, with one
hourly slot remaining and the next shown at 11:41 AM EST. No match-level results
were exposed. The public `score-3.25` tag preserves the prior baseline.
