# Revision 52: hold a safe retreat direction against lightning

Laser charging halves ground speed. Nearby opponents with lightning can
catch a pilot that repeatedly turns off its retreat line and interrupt the
beam. This candidate adds an unboosted, coherent retreat to the 4.50
early-combat controller.

It needs a single observed, advancing arc carrier, an active laser cycle,
and a lane that delays entry into range. It verifies the changing body
against the ground and circle, and gives up the route for a new firing
lane, incoming projectile, physical obstruction, or another active
movement objective. Weapons continue through the ordinary controller.

The public-map gun-and-arc feedback compares the full bot with and
without the direction change. At 55 m, the original 4.31 prototype
reduces real arc hits from five to two in the primary paired cases and
retains at least 400 HP at the end of the fight. The close and distant
controls keep their measured survival outcomes. The test models actual
movement and shots but does not measure practice placement.
