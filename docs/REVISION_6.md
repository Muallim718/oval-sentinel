# Revision 6: prefer lightning over laser

Baseline: revision 4, **3.21** placement points. This experiment changes only
secondary-weapon preference and safe replacement in `sentinel/strategy.py`.
It does not include the unsuccessful roof/matchup or shared-aim experiments.

## Hypothesis

Revision 4 rates lightning and laser equally and keeps whichever it finds first,
even when an idle laser could be replaced with nearby lightning. Lightning offers
instant cone attacks, chain damage, and no charging movement penalty. The existing
duel policy already knows how to approach lightning range. More consistently
equipping it may improve performance against the cooperating house squad.

This is a strategy hypothesis, not a diagnosed cause of specific deaths. Lightning
has shorter range and spends energy; closer fights may also make the bot easier
to hit. The scored comparison will decide whether this preference is useful.

## Isolated change

- Lightning's preference value increases from 3 to 4; laser remains 3, mortar 1.
- Existing goal scoring can therefore seek lightning when holding a laser.
- A nearby lightning pickup can replace an idle laser in slot 1. The gun is kept.
- A charging laser is never swapped. A replacement action suppresses the slot-1
  trigger for that action, so it cannot start a new laser charge during the swap.
- Lightning is not downgraded to laser or mortar. The bot still takes a laser
  when one is available and no better weapon is nearby.

Navigation, movement preferences, ordinary firing/aiming, duel selection, recovery
thresholds, cube policy, and upgrade priorities are unchanged from revision 4.
Their existing reactions to the newly held weapon still apply.

## Verification

Nine added tests cover equal-distance selection, safe replacement, charging-slot
protection, trigger suppression during a swap, retaining the gun, avoiding
downgrades, vertical pickup limits, laser fallback, and planning a lightning
upgrade. All 48 behavioral tests and the 300-observation official checker pass
locally. No win-rate or placement improvement is claimed before scored practice.

The requested 10:28 AM EST slot time had already passed when work began; the
candidate is to be submitted after Linux validation and live quota confirmation.
