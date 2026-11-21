# How Oval Sentinel plays

## Why survival comes first

Placement determines the score, and health can regenerate after five seconds
without dealing or receiving damage. Firing at a distant opponent while trying
to recover prevents that recovery. Sentinel therefore stops optional ranged
fights below 65% HP, while still defending itself at close range and fighting in
a final duel. That threshold is a preference in `tuning.py`, not a game rule.

In practice, the house bots cooperate and never damage each other. Merely hiding
does not guarantee placement points: eventually the bot must defeat pursuers or
outlast opponents in the zone. Sentinel combines safe loot collection with
selective fights rather than assuming the house bots will eliminate each other.

## Position selection

Every 1.2 seconds, the bot evaluates nearby positions, safe-circle positions,
its previous destination, and relevant visible loot. A goal is more expensive
when it is exposed to a known enemy, close to that enemy, outside the predicted
zone, or far away. A wall between the candidate and an enemy reduces its danger
cost. Current safe positions receive a small preference to reduce indecision.

The bot only knows enemies supplied in observations. Previously observed enemies
remain a declining threat estimate for up to 12 seconds. It never discovers an
unseen enemy through the map or infers private seeds.

Zone prediction interpolates from the **current** observed circle toward its
next circle. Reapplying the entire phase interpolation would double-count an
already elapsed shrink; a regression test covers that mistake.

## Getting there

A 6-meter grid marks ground positions that have enough clearance for the
starting mech. A* connects nearby cells only after checking the intervening body
path. Searches have both an expansion limit and a 9 ms time budget. If a search
cannot finish in one decision, its frontier survives into the next. This matters
for U-shaped obstacles, where a valid escape first moves away from the target.

Local steering checks the mech's current upgraded radius and height, considers
acceleration inertia, and chooses among alternate directions. It favors distance
from close enemies, dodges predicted projectile paths and charging laser lines,
and penalizes steps toward the storm. Sprinting has energy hysteresis so the bot
does not alternate boost on/off every decision. A stuck mech can jump and jet.

## Shooting

All weapons share one torso, and shots use its actual aim. A command to turn does
not mean the gun is already pointed there.

- **Gun:** solve the constant-velocity interception equation, estimate falling
  target height, check range and obstruction, and fire when the actual aim overlaps
  the target. Reload partly empty magazines while there is no firing opportunity.
- **Laser:** hold to charge, then release at full charge when aligned. Preserve a
  charge while the aim catches up. Avoid starting a charge during a close retreat,
  because charging halves movement speed.
- **Lightning:** require a target in range and the actual yaw cone, with sufficient
  energy remaining. Do not spend energy firing at empty space.
- **Mortar:** iteratively lead a moving target with a low ballistic arc, check
  segments along that arc for obstruction, and reject dangerously close shots.

The bot favors finishing damaged opponents and respects the same torso aim for
both slots. It faces known threats when there is no firing solution to reduce
rear-armor damage, even while its legs move away.

## Loot and upgrades

Visible cubes and nearby crates are useful only when collection is reasonably
safe. The bot rejects loot on a roof when it cannot simply walk to it. Weapons
must be within both the horizontal pickup radius and the fixed 4-meter vertical
pickup limit before a `take` action is sent. A nearby unobstructed supply drop can
be worth pursuing for healing and cubes, but the bot avoids known crowds.

Upgrade ordering favors servos, repair nanites, armor, and plating, followed by
energy improvements and weapon upgrades. Exact effects still come from the
server. The preference order is deliberately isolated in `tuning.py`.

## Honest limits

These choices are hypotheses until practice matches measure them. In particular:

- Navigation plans ground routes. Local checks support being on roofs and under
  bridges, but the bot does not plan a full network of roof-to-roof jet paths.
  Circles ending deep inside tall buildings can be difficult.
- Terrain, projectile dodging, and mortar collision checks use sampled
  approximations, not the authoritative server's complete physics.
- Cover checks ignore tree vision attenuation, conservatively assuming a known
  opponent might see through foliage. Trees do not stop bullets.
- Enemy motion prediction assumes constant horizontal velocity. Sharp dodges,
  knockback, and changing acceleration can cause misses.
- Enemy sound bearings protect facing after incoming damage, but the bot does not
  triangulate sounds into a complete map of unseen opponents.
- The kit replay does not react to our actions. Neither protocol compliance nor
  a low decision latency demonstrates a placement improvement.

Use scored practice failures to decide which limitation deserves the next change.
