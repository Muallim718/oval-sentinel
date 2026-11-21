# Revision 37: coordinate both weapons on one torso

This branch starts from the 4.04 submission. It replaces the direct-fire part
of a mech engagement with a scheduler that checks the upcoming two simulation
steps. The original farming, mortar, flight, and quiet recovery paths still
use their existing decisions.

The gun solution starts at the actual forward barrel. The trigger uses a
swept cylinder for the moving target, the torso's permitted turn and pitch,
and a terrain ray to the impact point. The scheduler tries the body center
first and checks a few interior points if geometry blocks it. This lets it
use an exposed upper body without blindly shooting through the obstacle.

Gun and secondary readiness use the observed cooldown. The controller
tests a shared aim when gun lead and laser aim differ slightly. A ready gun
can keep shooting while a laser cools or charges. A charged beam can release
early for a weak target or to get the mech moving at full speed again. After
damage, a ready lightning arc and the gun can fire together while the mech
still retreats, and a new laser charge cannot delay that retreat.

The public protocol gives two 50 ms simulation steps for each observation.
The predicted ray uses movement at the observed velocity during that brief
window and does not predict enemy evasive inputs or random spread. Airborne
engagements still fall back to the existing gravity-aware gun solver.

Focused tests cover barrel lead, turning into a shot before the next
observation, shared fire, charge release, exposed bodies, and cover. In the
four public-map two-wave cases, the two gun-only starts still lost their
first duel with the opponent at 5 HP. With the lightning pickup, one case
cleared both waves at 111.56 HP and one died with the second hunter at
152.77 HP. The initial pickup and first kills matched the 4.04 reference.
These are local combat checks. The practice score comes from the organizer's
48 matches.
