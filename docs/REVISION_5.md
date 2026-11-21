# Revision 5: gun/laser shared-aim coordination only

**Scored result: 3.13**, below the 3.21 baseline by 0.08 displayed points.
Receipt `BB-EC17A634` scored commit `4396a6c736ec00990fab35c2f6e6df4739f02410`,
submitted when the quota reopened at 10:12 AM EST on 2026-11-21.

The site kept revision 4 selected as the best entry. The runtime code on `main`
has been restored to revision 4. This experiment, its feedback tool, and its tests
are preserved on
[`experiment/shared-aim`](https://github.com/Muallim718/oval-sentinel/tree/experiment/shared-aim).
The implementation description below refers to that experimental branch.

Baseline: revision 4, **3.21** placement points. The only runtime file changed is
`sentinel/combat.py`. Navigation, movement, target scoring, weapon preferences,
loot, upgrades, and recovery policies are unchanged.

## Identified inefficiency

The gun needs to lead moving targets; a laser uses their present position. Both
weapons share the torso. Revision 4 aimed at the laser's hitscan point throughout
its charge, often leaving the gun outside its firing tolerance at longer ranges.

Revision 5 uses projectile lead during a laser charge when a loaded, non-reloading
gun has a solution to the same target. Once full charge is reached, it acquires
the laser's aim and releases only after the actual torso is aligned. It avoids
spending a gun round into an incompatible beam aim during that transition.
Without a usable gun, it keeps the original laser behavior.

## Controlled feedback comparison

`tools/weapon_feedback.py` runs a circular target around a stationary shooter in
an unobstructed field. It models aim slewing, both trigger states, gun magazines
and reloads, cooldowns, charge/release, projectile travel, and simple hit geometry.
It omits spread, cover, enemy attacks, and match dynamics. It is not the server.

For 30 seconds at 120 m and 12 m/s:

| Metric | Revision 4 | Revision 5 |
| --- | ---: | ---: |
| Gun hits | 45 | 66 |
| Gun shots during laser charge | 0 | 24 |
| Full-charge laser hits | 13 | 12 |
| Total modeled damage | 6,120 | 6,750 |

The extra transition time costs one laser shot in this scenario; the added gun
hits more than offset it. A sweep of 60/120/190 m and 0/6/12 m/s had no modeled
damage decrease: stationary cases were unchanged, and affected moving cases
improved by approximately 10–16%. This does not establish a placement gain.

Reproduce with `python3 tools/weapon_feedback.py --sweep`. Compare an archived
revision with `--project-dir PATH` using the same tool. Six new regressions cover
charge startup, gun leading while charging, acquisition before beam release,
empty/reloading gun behavior, stationary targets, and closed-loop weapon output.

All 45 behavioral tests passed locally and in the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44917131861).
The restricted-container official checker passed 300/300 observations with no
missed deadlines and a maximum response time of 12.7 ms. The crowded-input host
benchmark peaked at 26.11 ms; its growing-body variant peaked at 24.57 ms.

## Interpretation

The controlled damage gain did not produce a better practice score in this run.
The event provided no match-level outcomes to explain the difference. A small
0.08-point gap in one run does not distinguish a reliable loss from run variation,
nor identify a cause. The higher-scoring revision 4 is retained rather than
assuming the model's gain transfers to real games.

No additional submission was made. The page showed no hourly slots remaining
and the next one opening at 10:28 AM EST.
