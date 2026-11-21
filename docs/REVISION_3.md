# Revision 3: body-aware routing, matchup decisions, and roof recovery

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
