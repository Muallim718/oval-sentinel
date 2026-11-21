# Revision 43: acquire the laser and keep existing spacing

Revision 39 combined laser acquisition, distant fight spacing, and a weapon
upgrade selector. It scored 4.06, below its 4.19 starting point.

A separate public-map diagnostic places the same laser within reach of each
pilot. The 4.31 pilot clears both pursuit waves in both reachable-laser cases.
Revision 39 and the combined ranged and recovery candidate each clear one.
The cases without an acquired pickup still end in the first gun duel. These limited
tests motivate keeping the existing fight spacing once a laser is equipped.

This version starts with the 4.31 recovery controller. It uses the checked
laser acquisition route and protects an existing beam during an exposed
repair transition. Duel ranges and upgrade choices come from the 4.31
controller. Nearby free pickups still work while injured.

In the two reachable-laser cases, this candidate matches the 4.31 result,
including the same 2.4-second beam cadence during the second wave and
464.51 and 457.76 HP at the end of the two waves. The separate 90 m
acquisition test still reaches and equips the laser.
