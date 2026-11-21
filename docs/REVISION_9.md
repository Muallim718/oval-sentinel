# Revision 9: acquire equipment without fighting the objective

Baseline: revision 8, **3.63** placement points. This changes combat readiness and
safe free-resource acquisition together; the cover/motion redesign is retained.

**Outcome: 3.58**, 0.05 below the 3.63 baseline in this run. The policy was not
adopted; the default runtime was restored to revision 8. The complete tested
candidate remains on the public
[`experiment/readiness`](https://github.com/Muallim718/oval-sentinel/tree/experiment/readiness)
branch at commit `3a514776071bfe9bfd1972f82593dc42afa9e95e`.

## Evidence

On the kit's 300 recorded observations, revision 8 selected a weapon goal on 31
frames. On 30 of those frames it also adopted the 65 m closing posture for a
favorable duel, despite carrying only a gun against a gun-plus-laser opponent.
The weapon was approximately 113–134 m away. Movement could therefore be pulled
toward the opponent while the strategic objective was still to acquire equipment.

The replacement changes those 30 frames to `arm/weapon`. All 31 weapon-goal frames
and 221 cover-goal frames remain. This is an output audit, not a measurement of
new inventory: all 300 recorded self-states remain gun-only with zero cubes
because the recording does not react to our actions. No loot gain is inferred.

Reproduce with `python3 tools/audit_missions.py`; use `--project-dir` to inspect
an archived baseline with the same audit tool.

## Combat readiness

Gun-only mechs no longer voluntarily adopt the close-duel posture against an
opponent carrying a secondary. Defensive gun fire stays enabled. A healthy mech
with an already selected, still valid weapon mission uses `arm` posture and
ordinary risk-scored navigation instead of letting readiness alone replace that
mission with holding cover. This requires at least 90% HP, no incoming weapon
hit in the previous second, and threats at least 80 m away.

Recovery, crossfire, and close danger keep protection first. Close weak-target
finishes and final duels retain their exceptions. The doctrine is explicit and
does not depend on an arbitrary remembered pickup somewhere behind a wall.

Actual acquisition is observed separately from intention. After an empty-to-
secondary or changed-secondary transition, initial equip cooldown is respected
until the first ready observation. Later ordinary firing cooldowns do not put
the mech back into an equipping state.

## Secured free-resource corridors

`sentinel/provisioning.py` can extend a held shelter to collect a nearby cube or
useful weapon. It does not require every known enemy to be more than 95 m away;
it instead checks a short direct ground corridor:

- At most 45 m, live body/ground/zone valid, with firing-lane samples every 4 m.
- Torso/head/flank rays against relevant known enemies, using the shared cover
  geometry. A protected endpoint alone is insufficient.
- A conservative veto near visible NPC chase lanes and for incoming projectile
  trajectories crossing the sampled corridor, including fast bullets between
  observation sample times.
- At most six candidates and a 3 ms search budget; incomplete checks fail closed.

Every observation rechecks the plan. It cannot interrupt a shelter approach,
recent weapon damage, urgent zone rotation, a close finish, or the final duel.
Hurt mechs do not start optional attacks while following an approved free-loot
route: collecting a cube or pickup need not reset healing, while shooting a crate
would. This mechanism never enables special crate or NPC farming.

## Verification and limits

The merged candidate passed 109 local behavioral tests, including 15 provisioning
tests, 13 independent readiness/integration tests, and one coupled acquisition
feedback test. Official checker: 300/300
on-time answers, zero errors, maximum 6.0 ms. Synthetic crowded and growing-body
latency checks peaked at 17.50 and 14.69 ms on this Windows computer.

The independent tests include long-range mission preservation, healthy defensive
fire, crossfire and recent-hit overrides, first-equip versus later cooldowns,
zone urgency, a recovering final duel without a selected combat target, safe
free loot during healing, NPC lanes, and a 252 m/s bullet crossing between
quarter-second samples.

In the coupled feedback test, a recovering 700 HP mech follows a protected route
to a laser 20.4 m away, emits a valid `take` from 2.95 m after 1.3 s, and heals to
758.5 HP during that approach. Independent 20 Hz movement steps remain clear and
occluded, with no offensive fire or jump. The test ends at acquisition and does
not model secondary combat or predict placement.

These corridors are bounded geometric approximations, not a promise of safety:
unseen enemies, future movement, and visibility between samples remain uncertain.
The gun-only reactive lab cannot model secondary acquisition/combat, so its old
results are not used to claim a revision 9 score gain. Scored practice decides
whether the new readiness/resource policy is retained.

## Linux validation and scored entry

Commit `3a514776071bfe9bfd1972f82593dc42afa9e95e` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44927049932):
109 tests, the pinned image build, and 300/300 on-time restricted-container
responses, p99 5.1 ms and maximum 9.9 ms. The Linux host crowded and growing-body
benchmarks peaked at 26.52 and 16.02 ms, with no decisions above 50 ms. The
committed tree was 2,265,033 bytes, below 20 MB.

Receipt `BB-F0C28E64` was submitted at 11:55 AM EST on 2026-11-21 and scored
**3.58**, implying an average placement of approximately 12.42. The site kept
3.63 selected. This small aggregate decrease does not establish statistical
significance or show which component changed the outcome. Runtime sources on
`main` were compared with the 3.63 commit and match exactly after restoration.
