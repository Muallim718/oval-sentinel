# Revision 49: acquire threats before taking more rear damage

This version brings the sound and exposed-body decisions from revision 17
and the damage-bearing memory from revision 30 to the selected 4.31
controller. The active-attacker filter, movement, and repair checks still
choose when to engage.

An anonymous sound can turn the torso during a quiet scan. A real, attributed
hit can hold its bearing for up to 1.1 seconds when there is no workable fire
solution. The torso can take nearly 0.8 seconds to turn around. Holding this
bearing gives it time to bring the attacker into view and avoid rear damage
bonuses. A confirmed death clears the old bearing. A useful actual shot
continues to own aim.

If cover blocks the target center, the gun and laser can check an exposed
part of the same observed body and verify both the barrel ray and body
intersection. They still use actual aim and line of fire.
