# Revision 55: finish one opponent from behind a wall

A recovering mech with two attackers can sometimes move sideways to block
the stronger attacker's shots while keeping a short gun shot on the weaker
one. This version adds that option to 4.50. It checks a reachable wall-side
position, the health cost of getting there, and the available rounds. Actual
repairs, pickup routes, charged beams, and storm movement keep priority.

In the paired physical encounter, both pilots fire four rounds and defeat
the weak gunner at 0.80 seconds. The extra wall-side step leaves the pilot
with 620 HP instead of 552.5 HP at four seconds. When the weak opponent
starts in a real reload, both finish the window with 800 HP. The model
tests a specific crossfire layout, not whole practice placement.
