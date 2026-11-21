# Revision 2: sustained fire and deliberate objectives

The first scored bot earned 1.50 placement points. No per-match replay or death
breakdown was exposed, so a precise cause of that score cannot be established.
Code inspection and controlled tests nevertheless found concrete policy defects.

## Evidence and changes

| Finding | Change | Verification |
| --- | --- | --- |
| A gun cooldown removed its targeting option; a non-firing frame could trigger a half-magazine reload during combat. | Keep tracking between shots; only reload a partial magazine when quiet. | Recorded-stream audit and weapon-clock feedback test. |
| Looking away made visible loot disappear from goal scoring. | Remember observed items; commit to collection; clear stale nearby targets. | Look-away regression and wall-navigation collection test. |
| One fixed escape distance made lightning hard to use. | Engage favorable isolated opponents at weapon-specific distances; avoid multiple exposed enemies. | Lightning approach and crossfire tests. |
| Recovery could stop as soon as the low-HP threshold was crossed upward. | Recovery starts below 58% HP and ends at 90%. | Recovery hysteresis test. |
| A picked-up mortar was never replaced with a better secondary. | Allow a safe slot-1 swap to lightning or laser; preserve the gun. | Slot-selection regression. |
| Loot and crate rewards often lost to standing still. | Increase safe objective value, collect early cubes, farm accessible crates/drones, prioritize supply-drop healing. | Goal-selection and feedback tests. |

On the **same 300 recorded observations**, the original submitted commit
`d8e307a9dc89bf858edb40993daf15581a9afe2b` issued 103 partial-magazine reload
commands with an enemy visible. Revision 2 issued zero. Gun-trigger frames rose
from 17 to 24. These are policy-output counts, not actual rounds fired, damage,
or a placement prediction: the recorded observations do not react to our actions.

Reproduce the current audit with:

```sh
python3 tools/diagnose.py
```

An archived older project can be audited with `--project-dir PATH` using the same
tool. The improved regression suite includes simplified movement and weapon
feedback models derived from the published rules; it does not replace the game's
authoritative simulation or measure performance against the house squad.

## Remaining uncertainty

The scored practice run is the deciding comparison. The larger set of changes
addresses interacting defects but does not isolate each one's score contribution.
Ground-only strategic navigation and incomplete enemy-motion prediction remain
limitations. No near-top score is claimed before the scorer measures it.
