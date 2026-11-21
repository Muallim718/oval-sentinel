# How Oval Sentinel plays

## Why survival comes first

Placement determines the score, and health can regenerate after five seconds
without dealing or receiving damage. Sentinel starts seeking recovery below
58% HP and stays in recovery until 90% HP. While steering toward safety,
it can use both weapons against an observed pursuer. Once its present body
is sheltered or the bot observes real regeneration, it gives repairs priority.
Incoming rounds or an exposed laser can interrupt that window. Cube and upgrade
health increases are distinguished from regeneration.

The thresholds are preferences, not game rules. Hysteresis prevents premature
returns to combat after only a small amount of healing.

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
Healthy mechs engage a single exposed opponent when its recent attack, torso
aim, or approach signals a fight and the HP comparison is favorable. Nearby
and weakened enemies can also become targets. All observed enemies still count
toward crossfire, and two exposed opponents trigger evasive positioning.
Duel spacing depends on the
secondary weapon: lightning moves into arc range, while lasers keep more distance.
With more than eight mechs remaining, an isolated duel can continue below the
ordinary health threshold against a weaker opponent. The bot uses closer gun
spacing when it can close safely. Crossfire, incoming damage from another mech,
the storm, and sheltered repairs take priority over that commitment.

Observed loot is remembered when the bot looks away. Cubes expire from memory
after 25 seconds, weapons and crates after 60 seconds. Nearby unobstructed negative
observations and successful pickups remove stale items. Collection objectives are
committed for up to 12 seconds unless danger or zone movement invalidates them.

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

Recovery and crossfire can override ordinary goals with a committed ground
shelter derived from building walls. Torso, head, and cylinder-flank firing lanes
must all be blocked before a position is called sheltered. The planner holds real
protection, looks for more protected separation from a close pursuer, and rejects
failed approaches. Body growth, enemies rounding corners, and the predicted
circle can invalidate a refuge.

Local steering rolls out nine horizontal commands, including braking, using live
body dimensions and published acceleration in 50 ms steps. It weighs exposure,
route progress, projectile paths, charging laser lines, and the predicted zone.
It can stop behind a wall; remembered enemies no longer force perpetual orbiting
through that wall. Exposed healthy duels retain evasive motion. Sprinting has
energy hysteresis and stops near a shelter so the mech can brake. Ground shelter
commitments cancel stale jump/jet intent; ordinary stuck escapes remain available
outside those commitments.

While recovering in confirmed shelter, optional weapon attacks are suppressed,
including finish attempts and mortar arcs that would restart regeneration.
Trigger-off can still release a charge already in progress into the cover.

## Shooting

All weapons share one torso, and shots use its actual aim. A command to turn does
not mean the gun is already pointed there.

- **Gun:** solve the constant-velocity interception equation, estimate falling
  target height, check range and obstruction, and fire when the actual aim overlaps
  the target. Continue tracking during cooldowns. Reload partly empty magazines
  only in quiet conditions without a tracked close enemy; an empty gun reloads
  during combat. Misalignment alone is never treated as a reload window.
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

In the opening minute the bot can commit to one observed floor weapon, cube,
crate, or drone. It checks that the route fits its body and that combat is
unlikely to interrupt the pickup. It tracks a farm target until damage
confirms the kill, then looks for the dropped reward. A fast quiet scan helps
find the first resource sooner. [Opening examples](REVISION_16.md)

After a confirmed kill the bot briefly associates observed cube IDs with the
fight. It can collect them while recovering when a direct route beats the
nearest known opponent and the estimated damage leaves a useful health reserve.
It checks the predicted zone and whether the body will fit after the cubes make
it bigger. It reevaluates the route every tick. [Kill reward examples](REVISION_13.md)

Visible cubes and nearby crates are useful only when collection is reasonably
safe. The bot rejects loot on a roof when it cannot simply walk to it. Weapons
must be within both the horizontal pickup radius and the fixed 4-meter vertical
pickup limit before a `take` action is sent. A nearby unobstructed supply drop can
be worth pursuing for healing and cubes, but the bot avoids known crowds.

Upgrade ordering favors servos, plating, armor, gun damage/rate, and repair
nanites. Exact effects still come from the
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
