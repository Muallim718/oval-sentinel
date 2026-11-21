# Revision 8: make cover a behavior, not just a destination

Baseline: revision 7, **3.25** placement points. This is a substantial redesign of
ground positioning and local motion, built on the best scored combat policy.

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

Linux validation and the scored comparison will be recorded after completion.
