# Revision 41: route to a verified kill reward

The 4.31 controller collects observed kill rewards when the direct route can
fit the larger mech after pickup. A wall can block that line even when the
cubes are a short walk around the corner. This revision reserves a bounded
ground search for one blocked reward after checking the original direct routes.

The detour must reach a real pickup anchor near the observed cube. It checks
the path in both directions with the body size after nearby cubes, and checks
time, energy, storm clearance, competing mechs, and incoming damage before
letting salvage own movement. The route is checked again while the mech moves.
Only observed cubes associated with a confirmed recent kill can trigger it.

In a controlled public-map corner case, both pilots start from the same
recorded HP, ammo, position, and energy, and see the same five kill cubes.
The reference remains at two cubes and 258.3 HP at six seconds. The candidate
walks around the wall and acquires all five at 2.85 seconds, ending at seven
cubes and 538.3 HP. Both get the same 60.75 HP of actual regeneration. There
are no shots, jumps, or body collisions in that comparison.

Separate continuous wave trials show that the late corpse position can vary
with local path timing. The detour gives a concrete way to secure a blocked
reward. Placement is measured by the official practice service.
