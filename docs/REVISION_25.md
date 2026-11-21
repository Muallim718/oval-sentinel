# Revision 25 takes cover during an empty gun reload

The original measurements below used the 4.04 pilot. The retrial uses the
same reload movement on 4.31 and gives an actual repair window priority.

A gun reload lasts 2.4 seconds with the starting gun. The 4.04 controller
can still stand in an enemy firing lane throughout that gap. This version
looks for a nearby, physically reachable wall shadow when the gun is empty
or already reloading. It keeps the target and ordinary aim. It gives up
the detour as soon as the gun refills, another opponent closes, the shelter
loses protection, or an effective secondary weapon can fire.

The paired 20 Hz feedback begins with the last actual round of a magazine
firing at a reactive opponent. At two different buildings on the arena,
the bot has 180 to 315 more HP when the gun refills in all four held-out
runs. At 12 seconds, it has 0 to 135 more HP and its opponent has 0 to 225
less HP. The defensive route can delay re-engagement, and damage dealt
by six seconds varies. These cases exercise public map geometry, gun
reload, and reactive pursuit. They do not predict placement or how often
a wall is close enough during scored play.

Across six paired cases the mean gain was 240 HP at refill and 76 HP after
12 seconds. Opponents had 134 less HP on average at 12 seconds.

All 129 local tests passed. The official checker answered 300/300 on time,
with a 6.6 ms maximum. Crowded and growing-body maxima were 22.94 and
15.23 ms.
