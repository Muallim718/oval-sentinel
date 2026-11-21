# Revision 6: prefer lightning over laser

Baseline: revision 4, **3.21** placement points. This experiment changes only
secondary-weapon preference and safe replacement in `sentinel/strategy.py`.
It does not include the unsuccessful roof/matchup or shared-aim experiments.

**Result: 3.10**, 0.11 below the baseline in this run. The change was not adopted;
the default runtime was restored to revision 4. The complete tested candidate is
preserved on the public
[`experiment/lightning-preference`](https://github.com/Muallim718/oval-sentinel/tree/experiment/lightning-preference)
branch at commit `9172761d9f81632fddb8ede1c2b27e317d8fad24`.

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
upgrade. All 48 behavioral tests and the 300-observation official checker passed
locally and on Linux. The
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44920352185)
also built the pinned image and passed the restricted-container checker with
300/300 on-time answers, zero misses, and a maximum response of 9.6 ms.

The requested 10:28 AM EST slot time had already passed when work began; the
candidate was submitted at 10:41 AM EST after Linux validation and live quota
confirmation.

## Scored outcome

Receipt `BB-BC6740E8` completed with **3.10** placement points, equivalent to an
approximate average placement of 12.90. Revision 4's **3.21** remained selected as
the best entry. The observed board position was 174; one rolling-hour submission
slot remained, with another shown to free at 10:53 AM EST.

The aggregate result provides no match-level reason for the difference. A single
0.11-point decrease does not establish statistical significance, but it gives no
reason to replace the better scored baseline. No further practice submission was
used for this experiment. Runtime sources on `main` were compared against the
3.21 commit and match exactly after restoration.
