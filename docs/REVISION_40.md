# Revision 40: combine the ranged kit with recovery combat

This candidate starts from the official 4.31 controller and adds the ranged
laser acquisition and spacing policy from revision 39. Escape movement and
firing still have separate decisions. A current shelter keeps its silence,
while exposed movement toward cover can use the secondary.

The actual laser charges over several observations. Dropping its trigger
while it is partly charged releases a beam. If exposed regeneration begins
while a laser already has a valid hostile shot in progress, the bot finishes
that charge with the gun held. A new charge requires the usual combat decision.
The focused test runs through that transition at 10 Hz with an actual
observed HP increase and separate charged and released trigger states.
