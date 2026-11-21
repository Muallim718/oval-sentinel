# Revision 17: acquire the first contact and use the part that is exposed

The first shot can arrive before the baseline camera sweep sees its source.
Gun sound carries 320 m while vision extends 200 m. When the bot has no
observed attacker or active objective, it can briefly face a fresh sound
bearing. It groups nearby bearings over time, spends a cue after the actual
torso has looked across its uncertainty cone, and resumes the usual scan.
The bearing controls only the torso. A real combat target and the normal
damage response retain priority.

Once a mech is observed, the baseline suppresses a gun or laser shot if the
center ray is blocked. The new solver checks a few interior upper-body and
flank points after a blocked center shot. It requires the current boresight to
reach the predicted moving cylinder without hitting a wall. The gun check
includes projectile travel, the live body size, and the forward barrel offset.
Open center shots and mortar and lightning policy keep their existing rules.

In a controlled late-quiet 180 m gun encounter using the usual slow scan,
turning to the sound reveals the opponent at 0.70 s instead of 2.80 s. The
first valid firing opportunity comes at 0.90 s instead of 3.10 s, and facing
the hit reduces its damage from 67.5 to 45. This is a timing case, and the
existing faster opener can narrow the difference early in the match.

In separate 20 Hz feedback, a diagonal target moves behind a 7.2 m wall. The
baseline finds no shot. The candidate releases a real simulated gun round
that hits at 0.417 s for 45 damage. Both reject a 20 m wall. This establishes
the collision and actual-aim behavior for that geometry. The presence of
anonymous unrelated gunfire and unknown enemy movement limits sound and lead
inferences in actual practice.

All 141 tests passed locally, including the new sound, shot geometry, and
full Bot checks. The official checker answered 300/300 on time, with an 8.7 ms
maximum. Local crowded and growing-body maxima were 21.68 and 20.43 ms.

Commit `408be827c0a8e006e96107ce87380aeebd0c9e20` passed 141 Linux tests
and the pinned image build. The restricted container answered 300/300 on
time, with p99 9.2 ms and maximum 14.0 ms. The tree was 2,381,167 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44947547778)

The practice service accepted this commit at 4:08 PM EST on November 21,
2026, under receipt `BB-B682596F`. It scored **3.96**, 0.21 above its 3.75
base. The 4.04 committed-duel entry remained the selected submission.
