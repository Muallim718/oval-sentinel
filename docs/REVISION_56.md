# Revision 56: finish the target before ranking weapon preferences

The selected4.50 policy ranks target/weapon pairs together. An available arc's
preference can make a healthy close enemy outrank a nearly defeated attacker
that the loaded gun is already aimed at. A legal two-enemy reproduction turns
the torso away from a90HP target and initially fires neither weapon.

This candidate first admits a short gun finish on an already eligible observed
mech. It requires current torso alignment, a clear shot, loaded ammunition,
at most three conservatively armored rounds, and a short travel/fire clock.
Unknown armor receives the maximum allowed by the public upgrade configuration;
extra cube damage and rear bonuses are not assumed. Foreground mechs, NPCs and
crates can veto an otherwise clear world ray.

The target lease lasts at most1.25seconds, retaining the same observed target
through ordinary gun cooldown and in-flight HP feedback. It does not claim an
unobserved hit. A reload, loss of observation/geometry, real retreat or repair,
storm priority, unrelated held laser, new unseen attacker, or a new non-target
rear/laser/mortar hit gives control back. An expired attempt has a short cooldown.
Movement and mode selection are unchanged. A new laser/mortar setup yields to
the ready gun during this short finish; gun+arc keeps the same-target scheduler.

## Controlled feedback

The20Hz model starts from a declared late-fight snapshot: a1400HP gun+arc
player, a healthy gunner at(30,-10), and an already-wounded90HP gunner at(100,40).
Both hunters move, aim and emit real rounds from the first tick. The player is
already aimed toward the wounded attacker. No hit or damage event is fabricated
to admit the feature. Static, reload, armor, lost-sight, wall and real rear-hit
controls exercise its rejection rules.

| Weak armor / seed | Original weak death | Candidate weak death | Original HP at6s | Candidate HP at6s |
|---|---:|---:|---:|---:|
|0 /47|5.40s|0.55s|635|860|
|0 /71|5.60s|1.05s|725|770|
|.24 /47|5.55s|0.80s|590|770|
|.24 /71|5.75s|1.30s|680|680|

The final armored case is neutral on remaining HP; no blanket improvement is
claimed. Its final round arrives after the target lease, illustrating that a
1.25second override is not a guaranteed kill deadline. Every case has zero
healing, ignored jumps or body penetration. Both policies use the same physical
shot/collision and automatic empty-reload rules. The model approximates movement
and ordering, omits kill rewards and other participants, and does not predict
practice placement. The starting wounded target's frequency in private matches
is unknown.

Run a paired diagnostic with an untouched selected checkout:

```powershell
py -3.13 tests/test_finish_target_feedback.py --simulate . candidate.json
py -3.13 tests/test_finish_target_feedback.py --simulate ../selected-4.50 baseline.json
```

## Verification

All189 local tests passed, including17 new focused/feedback tests. The official
checker answered300/300 on time, p99 6.4ms and maximum7.7ms. Synthetic crowded
and growing-body maxima were11.96ms and32.76ms, with no answer above50ms.
The finish selector alone took at most0.389ms over200 adversarial15-mech calls.
Linux validation and an official scored comparison remain outstanding.

This is original code based on published mechanics and Oval Sentinel's own
reproduction. No public comparator source or action provider is used.
