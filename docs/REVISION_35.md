# Revision 35 waits for evidence before opening an optional fight

A visible mech can be passing or watching another direction. The original
controller can open fire on it because it has a clear shot. This candidate
looks for a recent hit from that mech, torso aim toward us, or approach
speed and orientation consistent with an attack. Very close enemies, a
clear finish, and the last opponent remain eligible.

The remaining visible mechs still contribute to route and crossfire safety.
The new filter applies to initiating a duel and selecting weapons targets.
Drone, crate, resource, and ordinary recovery decisions keep their own rules.

One public competition report describes a 0.23 practice gain from a comparable
aggression filter in that team's bot. That report motivates testing the
mechanism here. The filter and its tests are part of Oval Sentinel's own
implementation. [Public practice notes](https://github.com/jackbalseca/mech-royale-bot/blob/de30a0d452125288a5ae231e500d4e27403e0f70/LEARNINGS.md)

All 128 local tests passed. The official checker answered 300/300 on time,
with a 7.6 ms maximum. Crowded and growing-body maxima were 17.41 and
20.81 ms.

Exact commit `95a644460964134a3f3684b8e2ed45f4bf6e403c` passed
[Linux and the restricted container](https://github.com/Muallim718/oval-sentinel/actions/runs/44954289870).
The container answered 300 of 300 observations on time, with p99 8.5 ms and
an 11.4 ms maximum.

Practice receipt `BB-8312DB68` scored **4.19** at 5:17 PM EST on November 21,
2026. That raised the selected score by 0.15 points from 4.04 and corresponds to
approximately 11.81 mean placement across 48 matches. The site automatically
selected this entry. The aggregate score does not identify individual match
outcomes.
