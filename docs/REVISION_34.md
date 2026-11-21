# Revision 34 boosts only when a visible round would otherwise hit

The original steering controller chooses whether to sprint before evaluating
its movement candidates. A healthy mech that has reached its fighting range
often evaluates only walking commands. A visible round can arrive before any
of those commands move the mech's body far enough away.

The new check evaluates the ordinary command against the visible gun rounds.
When that path intersects an incoming round, it considers a few short boost
sidesteps using the live body, acceleration, and remaining energy. It checks
the full movement against ground, walls, and the future zone. It commits to
the dodge for about 0.35 seconds so the extra speed has time to take effect.
Aim, fire, and the ordinary fight objective are preserved.

In a controlled 20 Hz encounter, both policies start with the same lateral
walking command. A real simulated gun round hits the walking mech for 45
damage after about 0.26 seconds. Using boost with the same direction avoids
the hit and spends 6.8 energy. The controls also test harmless, occluded,
and distant rounds, already-boosting movement, low energy, live body growth,
and a laser charge transition.

The helper did not activate in four paired matches in the short-range
two-wave diagnostic. The gunner starts at 55 m there and often leaves too
little time to move after a visible round arrives. Those runs offer no
evidence of a short-range placement gain.

Public competition notes independently report a score decline when that
team removed boost from its projectile dodge. That result motivates this
test of the original Oval Sentinel implementation.
[Public practice notes](https://github.com/jackbalseca/mech-royale-bot/blob/de30a0d452125288a5ae231e500d4e27403e0f70/LEARNINGS.md)

All 138 local tests passed. The official checker answered 300/300 on time,
with a 6.2 ms maximum. Crowded and growing-body maxima were 21.91 and
22.86 ms.
