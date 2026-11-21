# Revision 4: body-size-aware routing only

This is an isolated experiment on top of the proven revision 2 policy (3.06).
Revision 3's roof escapes and weapon-matchup decisions are not included.

## Runtime changes

- `sentinel/navigation.py` now consumes current radius and height. When they
  grow, it clears cached paths, search state, links, and clearance results.
- Previously base-valid grid cells are rechecked lazily with the larger body.
  Neighbor edges and direct-path smoothing also use the current dimensions.
- Before growth, cell validation keeps the original fast path; an unchanged body
  does not discard routes or searches.
- `sentinel/strategy.py` adds one call to pass `self.stats` to the navigator.

The game only enlarges living mechs through cubes, so a cell invalid for the
starting body need not be reconsidered as a valid cell later. The grid resolution
and all route cost preferences remain those of revision 2. Combat, loot memory,
goal selection, recovery thresholds, upgrades, and fallback jets are unchanged.

## Checks

Six new regressions cover unchanged-body stability, cached passage invalidation,
height under a bridge, a full route around an enlarged body's impassable gap,
successive growth invalidation, and the strategy-to-navigation integration.

All 39 tests passed locally. The official checker answered 300/300 observations
within budget, with zero malformed messages or wrong ticks. The growing-body
crowded-input benchmark exercises six sizes while providing 15 opponents and
32 projectiles. These synthetic inputs do not simulate a match or predict score.

## Scored outcome

Receipt `BB-1B78B4C1` scored commit `55e2f3b557db4e93df80f4b7ee0fa2f749327a07`
at **3.21**, up from revision 2's **3.06** (+0.15 displayed placement points).
The site selected revision 4 as the new best entry. The observed board position
was 169 of 251 teams. The four hourly slots were exhausted; the next one was
shown as becoming available at 10:12 AM EST.

The [Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44916162390)
passed 39 tests and the restricted-container official check: 300/300 on-time
answers, maximum response 13.0 ms. The growing-body synthetic benchmark peaked
at 24.81 ms on the Linux host, outside the restricted container.

The body-size-only change is retained on the default branch. Combat and other
strategy behavior still matches revision 2. This is a modest aggregate improvement
on the fixed practice set, not proof of statistical significance, causation in
individual matches, or an improvement on unseen final seeds. No match-level
breakdown was exposed.
