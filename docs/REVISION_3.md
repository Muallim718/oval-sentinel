# Revision 3: body-aware routing, matchup decisions, and roof recovery

**Outcome: 2.58**, below revision 2's **3.06** (-0.48 points, about -15.7%).
Receipt `BB-7E1019E7` scored commit `865fdb89536051f9df6a5ed65990dcb55dafa28f`.
The site retained revision 2 as the selected best entry. One hourly attempt
remained immediately afterward.

After this result the default branch was restored to revision 2. The subsequent
revision 4 isolates body-size-aware routing and scored 3.21. The full revision 3
experiment and its tests remain public on
[`experiment/roof-recovery`](https://github.com/Muallim718/oval-sentinel/tree/experiment/roof-recovery).
This document records an experiment that did not improve the score, not the
default policy's behavior.

Revision 2 scored **3.06**. The event exposes an aggregate score, so the code and
controlled feedback tests identify defects; they do not establish which defect
caused each death in scored practice.

## Concrete weaknesses addressed

1. **Navigation cached starting dimensions.** Cubes enlarge the mech, but the
   route graph still treated it as the starting cylinder. Revision 3 invalidates
   routes when live body dimensions change and lazily checks cells and edges with
   the new dimensions. This stays within the per-decision work budget.
2. **Duel selection compared health, not firepower.** Equal HP no longer makes
   our gun-only mech treat a gun-plus-laser opponent as an even fight. The estimate
   uses sustained gun magazines/reloads, both weapon slots, live own upgrades,
   cube scaling, enemy base stats, armor, range, and the laser/mortar signature.
   Enemy upgrades are not observable, so the estimate remains approximate.
3. **Escape jets were reactive and had no landing plan.** Revision 3 can plan a
   nearby roof refuge before committing energy. It approaches an outside launch
   column, ascends clear of the edge, crosses to an inset landing point, brakes,
   lands, and recovers without firing. No attacks are started while trying to heal.

The escape controller checks the current body, an overhead-clear column, a clear
crossing, energy for ascent plus crossing and a reserve, and a predicted safe
zone. It rejects occupied roofs, cancels when the zone invalidates the refuge,
and abandons flights with no vertical progress. A mortar is dropped from slot 1
when escaping a known laser carrier to avoid cook-off; the gun is retained.

## Scope and verification

`sentinel/elevation.py` handles nearby single-roof escapes, not arbitrary aerial
pathfinding or roof-to-roof traversal. Initial map preprocessing finds 93 potential
sites with the standard starting body; each is rechecked with live dimensions
and energy before use. The bot only considers a refuge under pressure or while
recovering from a known nearby threat. The proven revision 2 ground behavior
remains the fallback.

Tests exercise 12-, 25-, and 40-meter flights with acceleration, gravity, energy
drain/regeneration, and landing feedback. Additional feedback tests sample four
sites on the actual public map. Other regressions cover ceilings, occupied roofs,
energy rejection, growing-body clearance, zone cancellation, stalled jets,
regeneration-safe triggers, and upgrades during escape.

These feedback models are deliberately limited: they are not the authoritative
server and do not reproduce combat or all eave/ledge collision details. The
new scored practice submission is the deciding performance comparison.

## What the result establishes

The experimental build passed all 47 tests and the restricted Linux protocol
check (300/300 on-time answers, maximum 13.3 ms). Its synthetic crowded-input
benchmark peaked at 30.77 ms on that Linux host, outside the restricted container.
Protocol success and controlled flight success did not transfer to a higher
placement score.

No individual-match outcomes were exposed. The combined result does not establish
which of the roof controller, matchup restrictions, body-size changes, or their
interactions caused the regression. In particular, the flight feedback tests do
not model enemy attacks during takeoff, and enemy upgrades are unknown to the
matchup estimate. These remain hypotheses, not measured causes of death.

The next useful scored comparison should isolate a small change against revision
2, such as the body-clearance correction alone, rather than adding another large
bundle. No additional practice attempt was consumed after this result.
