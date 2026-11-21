# Revision 24 fixes the ready mortar aim deadlock

Revision 58 applies this same mortar behavior to the scored 4.50 early
equipment and upgrade controller. The physical comparisons below isolate
the original shared-aim problem.

The mortar can own the only torso aim while its fixed alignment gate
keeps refusing to fire. At 45 m a sprinting transverse mech can turn the
desired angle more than the gate permits between observations. The gun
points at a different lead and can fail to fire for the same interval.

The existing alignment path remains available. When it refuses a ready
mortar, a bounded trace checks the moving target cylinder, forward barrel,
terrain, and self-splash. The trace must reach the body under each plausible
ordering of target motion, torso slew, and first emission. If the shot
remains unproved across three observations, the gun gets four aim updates
when it has a valid shot at the same target. A validated mortar can take
over sooner.

In the 45 m sprinting case, the 4.04 policy fired neither weapon in two
seconds. The new policy still withholds the uncertain mortar and lands
three or six real gun hits, depending on firing order. At 30 m and the
ordinary 11.7 m/s walk speed, it lands a 360 damage direct shell under
both orders. When a low overhang blocks the actual mortar barrel, the
gun gets four decisions and lands one hit before 0.6 seconds. These
cases use public movement and projectile constants and a physical hit
test. The actual ordering of events on the server is undocumented.

All 134 local tests passed. The official checker answered 300/300 on time,
with a 6.3 ms maximum. Crowded and growing-body maxima were 19.58 and
23.91 ms.
