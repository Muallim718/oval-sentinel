# Validation performed

## Current default: restored 3.63 controller

The runtime, tests, ground feedback tool, and verification command on `main`
match the scored `9bf75d70a8d209a1dd8ea4f67415ee93a9cbf7f0` exactly. The
readiness and rooftop experiments remain on public branches with their scores
and evidence below. They are not part of the default bot.

After restoration, all **80 tests passed locally**; the official checker
returned **300/300 on-time answers**, zero errors, startup 231 ms, p99 3.5 ms,
maximum 9.3 ms. Crowded/growing-body host maxima were 21.38/22.00 ms, with no
decisions above 50 ms. The unchanged runtime's original Linux sandbox check is
linked in the revision 8 section; GitHub Actions also repeats it for this push.

## Revision 12: projectile-aware duels

The candidate improved health and kill outcomes in the limited reactive gun
model, then scored **3.38** in actual practice against the selected 3.63 entry.
Both local and Linux runs passed 107 tests. The official checker returned
300/300 on-time restricted-container replies, with a 13.7 ms maximum.
[Design, case comparisons, and practice result](docs/REVISION_12.md)

## Revision 11: phase-aware roof zone control


**Experimental, not the default:** scored **3.31**. Revision 8's 3.63 entry
remains selected, and its runtime and test suite were restored exactly on
`main`. The roof candidate is public on `experiment/roof-zone`.

This corrects revision 10's abandoned-launch zone requirement after landing.
It retains or repositions a supported live hold on the same roof and preserves
physical exit ownership and weapon-pressure guards. See [the change and its
limits](docs/REVISION_11.md).

- All **141 tests passed locally**, including 24 new zone cases and one
  additional actual-body-fit case. Seven earlier flights still pass.
- Local official checker: **300/300 on-time**, zero errors; startup 409 ms,
  p99 3.6 ms and maximum 9.1 ms.
- Crowded/growing-body local host maxima: 22.83/12.87 ms, zero above 50 ms.
- Forty quiet starts: 12 plans, maximum decision 2.91 ms and startup 489.3 ms.
- Active roof-zone timing: 160 updates, 40 public roofs, p99 5.98 ms, maximum
  6.65 ms, zero above 50 ms. This measures the altitude controller on the host,
  excluding the rest of the bot and protocol I/O.

Commit `c70818c75148d369b713e03010cbce44bf0ac4e8` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44932195013).
All 141 tests and the pinned image build passed. The restricted-container
official checker returned 300/300 on-time, p50 2.5 ms, p90 3.6 ms, p99 7.2 ms,
maximum 16.6 ms. Linux host crowded/growing maxima were 31.21/31.13 ms;
quiet-start decision maximum 4.49 ms; active roof-zone p99 12.35 ms, maximum
14.02 ms. No samples exceeded 50 ms. The submitted tree contains 61 files,
2,344,126 bytes, below 20 MB.

Receipt `BB-002475DD` was submitted at 12:52 PM EST on 2026-11-21 and scored
**3.31**, implying average placement approximately 12.69. This is 0.09 below
the original roof experiment and 0.32 below the best controller. Correcting the
demonstrated zone flaw did not improve aggregate placement; no match-level
breakdown established why. Runtime, tests, and verification tools were compared
with `9bf75d70a8d209a1dd8ea4f67415ee93a9cbf7f0` and match exactly after restoration.

## Revision 10: proactive roof sanctuary

**Experimental, not the default:** scored 3.40 and archived on
`experiment/proactive-roofs`. Revision 11 corrected its zone behavior and scored
3.31; both roof versions are below the retained 3.63 ground controller.

Commit `7edf73c69c0661c98cc1f2fd53096af62d130bf9` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44930483153).
This adds early roof access/holding/physical exits to revision 8's 3.63 policy;
revision 9's unsuccessful readiness/resource policy is not included.

- All 116 behavioral tests passed locally and on Linux: previous 80, eight
  roof-core tests, ten independent physics/flight tests, and eighteen integration
  tests. Seven complete flight traces cover 12/25/40 m synthetic roofs and four
  public-map roofs; the 40 m case retains 29.5 energy from an initial 100.
- Local official checker: 300/300 on-time answers, maximum 9.1 ms.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 1.8 ms, p90 2.6 ms, p99 5.7 ms, maximum 14.0 ms on that runner.
- Linux host crowded/growing-body maxima: 25.87 and 16.06 ms, zero above 50 ms.
- Separate quiet-map search benchmark on Linux: 40 fresh bots, 12 roof plans;
  maximum decision 3.54 ms, maximum startup 558.3 ms, zero decisions above 50 ms.
  This exercises proactive search rather than the nearby-hunter veto.
- Committed source: 56 files, 2,303,209 bytes, below 20 MB.

Flight feedback models whole-body ceilings, walls, jumps, jets, energy, and roof
edge support, but not authoritative combat or exact server eave resolution.
These results establish tested control behavior, not scored performance.

Receipt `BB-7E1DFF95` was submitted on 2026-11-21 at 12:33 PM EST after these
checks and scored **3.40**, implying average placement approximately 12.60.
Revision 8's 3.63 remains selected. Post-submission code review found that the
zone check can abandon a safe roof because the old ground launch is outside
the future circle. This is a demonstrated control flaw, not an established
explanation of the aggregate score. The submitted candidate is preserved on
`experiment/proactive-roofs` for comparison with a correction.

## Revision 9: readiness and secured resource acquisition

**Experimental, not the default:** scored **3.58**, 0.05 below revision 8's
3.63. Revision 8 remained selected, and its runtime was restored on `main`.

Commit `3a514776071bfe9bfd1972f82593dc42afa9e95e` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44927049932).
The revision adds explicit combat readiness, preserves healthy accepted arming
missions, and permits free nearby loot along a rechecked protected corridor.
Revision 8's 3.63 controller is preserved by the public `score-3.63` tag.

- All 109 behavioral tests passed locally and on Linux: the previous 80,
  15 provisioning tests, 13 independent readiness tests, and one coupled
  physical acquisition test.
- Local official checker: 300/300 on-time answers, maximum 6.0 ms.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 1.9 ms, p90 2.5 ms, p99 5.1 ms, maximum 9.9 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: maximum 26.52 ms;
  growing-body variant: maximum 16.02 ms. No decisions exceeded 50 ms.
- Committed source: 53 files, 2,265,033 bytes, below 20 MB.
- Recorded posture audit: 30 gun-only `fight/weapon` frames become `arm/weapon`;
  all 31 weapon goals and 221 cover goals remain. Inventory is recorded, so no
  acquisition or score improvement can be inferred from those output counts.
- In a limited independent 20 Hz feedback test, the hurt mech takes a laser
  20.4 m along a protected corridor after 1.3 s, within 2.95 m; HP rises from
  700 to 758.5, with no offensive fire. Secondary combat is not modeled.

Receipt `BB-F0C28E64` was submitted on 2026-11-21 at 11:55 AM EST after these
checks and scored **3.58**, implying an average placement of approximately 12.42.
The small difference does not establish statistical significance, and no match
breakdown was exposed. The complete candidate remains public on
`experiment/readiness`. After restoration, runtime sources were compared against
`9bf75d70a8d209a1dd8ea4f67415ee93a9cbf7f0` and match exactly.

## Revision 8: cover and motion redesign

**Retained:** scored **3.63**, up 0.38 displayed points from revision 7's 3.25.
The site selected this entry as the team's best.

Commit `9bf75d70a8d209a1dd8ea4f67415ee93a9cbf7f0` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44924563407).
The redesign adds ground shelter planning, shared body-silhouette firing-lane
checks, predictive horizontal steering with braking, and recovery integration.
The 3.25 baseline is preserved by the public `score-3.25` tag.

- All 80 behavioral tests passed locally and on Linux: the previous 48 plus
  20 cover and 12 motion/integration tests.
- Local official checker: 300/300 on-time answers, maximum 8.7 ms.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 1.9 ms, p90 2.5 ms, p99 5.8 ms, maximum 14.0 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: maximum 16.74 ms;
  growing-body variant: maximum 26.83 ms. No decisions exceeded 50 ms.
- Committed source: 47 files, 2,218,632 bytes, below 20 MB.
- Independent ten-second fixed-shelter motion test: no drift, exposure, or boost
  spending. The old steering moved roughly 136 m with a fixed protected goal.
- A corrected, limited reactive gun-pursuit model improved all eight wall-pressure
  cases over four seeds; mean modeled death time approximately 7.38 to 15.26 s.
  Pressure cases still died before 25 s. Quiet collection stayed at 12.35 s.
  These invented opponents and approximate physics cannot predict placement.

Receipt `BB-1461B1AF` was submitted on 2026-11-21 at 11:27 AM EST after these
checks and scored **3.63**, implying an average placement of approximately 12.37.
Observed rank was 156 when read. One hourly slot remained, with another shown to
free at 11:41 AM EST. No individual match breakdown was exposed; the result does
not isolate the contribution of each part of the coherent movement redesign.

## Revision 7: recovery gun self-defense checks

**Retained in revision 8's baseline:** scored **3.25**, compared with revision
4's **3.21**. It was selected as the best before revision 8 scored higher.

Commit `08489ae01066524d475337a53ba20ee4d5c32724` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44921586744).
Only `sentinel/strategy.py` and `sentinel/combat.py` changed among runtime sources
relative to revision 4: briefly permit gun retaliation during recovery after an
incoming weapon hit. Movement, routing, equipment preference, and upgrades retain
the 3.21 version's logic.

- All 48 behavioral tests passed locally and on Linux, including nine recovery
  self-defense cases and a limited weapon-clock pressure test.
- Local official checker: 300/300 on-time answers, maximum 8.1 ms.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 0.7 ms, p90 2.2 ms, p99 7.7 ms, maximum 12.8 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: maximum 24.91 ms;
  growing-body variant: maximum 24.60 ms. No decisions exceeded 50 ms.
- Committed source: 40 files, 2,141,917 bytes, below 20 MB.
- Recording audit: 194 recovery frames for both versions; 45 followed recent
  weapon damage. Recovery gun-trigger frames rose from 0 to 3. The recording
  does not react to actions and cannot predict damage or placement.

Receipt `BB-3CD4B274` was submitted on 2026-11-21 at 10:54 AM EST after these
checks and scored **3.25**, implying an average placement of approximately 12.75.
The 0.04-point increase does not establish statistical significance. No
match-level breakdown was exposed. The observed board position was 173, with
one hourly slot remaining and the next shown to free at 11:12 AM EST. Only one
practice attempt was used for this change. The prior 3.21 entry remains public.

## Revision 6: lightning preference checks

**Experimental, not the default:** scored 3.10 versus revision 4's 3.21. Revision
4 remains selected, and its runtime sources were restored on `main`.

Commit `9172761d9f81632fddb8ede1c2b27e317d8fad24` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44920352185).
Only `sentinel/strategy.py` changed among runtime sources relative to revision 4:
lightning preference and safe replacement of an idle laser in slot 1.

- All 48 behavioral tests passed locally and on Linux, including nine weapon
  preference and replacement cases.
- Local official checker: 300/300 on-time answers, maximum 5.0 ms.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 0.9 ms, p90 2.8 ms, p99 7.1 ms, maximum 9.6 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: maximum 28.71 ms;
  growing-body variant: maximum 28.53 ms. No decisions exceeded 50 ms.
- Committed source: 38 files, 2,129,603 bytes, below 20 MB.

The synthetic inputs are latency checks, not scored matches. No individual death
cause or placement improvement can be inferred from them.

Receipt `BB-BC6740E8` was submitted on 2026-11-21 at 10:41 AM EST, after the
requested 10:28 slot time and completion of Linux checks.
The run completed at **3.10**, implying an average placement of approximately
12.90. The 0.11-point decrease does not establish statistical significance, and
no match-level breakdown was exposed. The 3.21 entry stayed selected; its observed
board position was 174. One hourly slot remained when the result was read.

The complete experiment is public on `experiment/lightning-preference`. After
restoration, `bot.py`, `mechfight.py`, and all `sentinel/` sources were compared
with revision 4 commit `55e2f3b557db4e93df80f4b7ee0fa2f749327a07` and match exactly.
The restored default passed all 39 local tests and the official checker again:
300/300 on-time answers, maximum 8.4 ms, no malformed or wrong-tick responses.

## Revision 5: shared gun/laser aim checks

**Experimental, not the default:** scored 3.13 versus revision 4's 3.21. Revision
4 remains selected, and its runtime sources were restored on `main`.

Commit `4396a6c736ec00990fab35c2f6e6df4739f02410` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44917131861).
Only `sentinel/combat.py` changed among runtime sources relative to revision 4.

- All 45 behavioral tests passed locally and on Linux.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 0.7 ms, p90 2.1 ms, p99 7.7 ms, maximum 12.7 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: maximum 26.11 ms;
  growing-body variant: maximum 24.57 ms. No decisions exceeded 50 ms.
- Committed source: 38 files, 2,130,311 bytes, below 20 MB.
- The controlled circular-target model increased combined damage from 6,120 to
  6,750 at 120 m and 12 m/s over 30 seconds. Gun hits rose from 45 to 66;
  full-charge laser hits fell from 13 to 12. A nine-case range/speed sweep had
  no modeled damage decrease. This is not an authoritative match simulation.

Receipt `BB-EC17A634`, submitted on 2026-11-21 at 10:12 AM EST after the quota
reopened, scored 3.13. The implied average placement is approximately 12.87.
The observed 0.08-point difference does not establish statistical significance.
No match-level breakdown was exposed. Revision 4's 3.21 remained selected, and
the next slot was shown at 10:28 AM EST.

The complete experiment is public on `experiment/shared-aim`. After restoration,
`bot.py`, `mechfight.py`, and all `sentinel/` sources were compared with revision
4 commit `55e2f3b557db4e93df80f4b7ee0fa2f749327a07` and match exactly.

## Revision 4: body-size-only checks

Commit `55e2f3b557db4e93df80f4b7ee0fa2f749327a07` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44916162390).
Only `sentinel/navigation.py` and one integration call in `sentinel/strategy.py`
changed among runtime sources relative to revision 2. Combat, loot, upgrades,
recovery, and movement preferences remained unchanged.

- All 39 behavioral tests passed locally and on Linux.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 0.7 ms, p90 2.1 ms, p99 7.8 ms, maximum 13.0 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: p99 19.91 ms,
  maximum 24.91 ms, zero decisions above 50 ms.
- Additional six-size growing-body benchmark on the Linux host: p99 23.84 ms,
  maximum 24.81 ms, zero decisions above 50 ms.
- Committed source: 35 files, 2,114,455 bytes, below 20 MB.

The synthetic benchmarks were outside the restricted container; the official
stream was checked inside it. Neither benchmark predicts scored placement.

### Revision 4 scored outcome

Receipt `BB-1B78B4C1`, submitted on 2026-11-21 at 9:53 AM EST, scored **3.21**
on that verified commit. This is +0.15 displayed points over revision 2's 3.06;
the implied average placement is approximately 12.79. The observed ranking was
169 of 251 teams. The site selected revision 4 as the best entry. No hourly
slots remained; the next was shown at 10:12 AM EST. The isolated change is retained.

## Revision 3 checks

**Experimental policy, not the default:** it scored 2.58 and was reverted in favor
of the proven revision 2 policy (3.06). The experiment remains on the public
`experiment/roof-recovery` branch.

Bot commit `865fdb89536051f9df6a5ed65990dcb55dafa28f` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44915257926).

- 47 behavioral tests passed locally and on Linux, including 12-, 25-, and
  40-meter flight feedback and four sampled public-map roof sites.
- Live-body route tests reject passages after body enlargement. Matchup tests
  distinguish equal-health opponents with different weapons and cube scaling.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 1.1 ms, p90 2.8 ms, p99 7.0 ms, maximum 13.3 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: p99 26.21 ms,
  maximum 30.77 ms, zero decisions above 50 ms. This benchmark was outside the
  restricted container; only the official stream ran inside it.
- Committed source: 35 files, 2,128,034 bytes, below 20 MB.

The feedback models are limited tests, not the authoritative match engine.

Receipt `BB-7E1019E7` was submitted on 2026-11-21 at 9:42 AM EST and completed
with 2.58 placement points (-0.48 compared with revision 2). The site kept receipt
`BB-F2A7BF5E` selected as the best entry. One rolling-hour attempt remained.
At the revision 3 rollback, the runtime sources were compared against
`0e193ba66fdca8f9b075ffbb1fc6a32b46b4a7f7`: `bot.py`, `mechfight.py`, and all
`sentinel/` files match the proven revision 2 version exactly.

## Revision 2 checks

Bot commit `0e193ba66fdca8f9b075ffbb1fc6a32b46b4a7f7` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44913981578).

- 33 behavioral tests passed locally and on Linux, including controlled feedback
  tests for cube collection around a wall and full-magazine sustained fire.
- Restricted-container official checker: 300/300 on-time answers, zero misses;
  p50 1.2 ms, p90 4.2 ms, p99 10.9 ms, maximum 17.2 ms on that runner.
- Synthetic crowded-input benchmark on the Linux host: p99 31.95 ms,
  maximum 36.33 ms, zero decisions above 50 ms. This benchmark was outside the
  restricted container, as in the original workflow.
- Committed source: 32 files, 2,098,802 bytes, below the 20 MB limit.
- The same-stream policy audit changed enemy-visible partial-magazine reload
  commands from 103 to zero. These counts are not actual match damage or score.

### Revision 2 scored outcome

Receipt `BB-F2A7BF5E`, submitted 2026-11-21 at 9:28 AM EST, completed with
**3.06** placement points on that verified commit. That is +1.56 points (+104%)
over the original 1.50. Approximate implied average placement: 12.94. The observed
board position was 173 of 249 teams, and the site selected it as the current best
entry. No match-level breakdown was exposed. Two hourly submission slots remained.

The original version's validation and first practice result follow below.

Prepared and tested on **2026-11-21** on Windows with Python 3.13.
These are local observations, not results from the scorer's Linux sandbox.

## Passing checks

| Check | Observed result |
| --- | --- |
| Behavioral regressions | 21 tests passed. |
| Official `check/check.py` | PASS: 300/300 observations answered within 50 ms. |
| Official checker response latency | p50 0.4 ms; p90 1.1 ms; p99 2.3 ms; max 3.2 ms. |
| Official checker startup | Ready in 218 ms, versus the 20,000 ms hello budget. |
| Protocol errors | Zero wrong ticks, bad lines, or stale queued responses in this run. |
| Debug-enabled official checker | PASS: 300/300 answers, max 3.4 ms, 300 drawings, zero cap violations. |
| Recorded direct-call benchmark | 300 decisions; p99 2.25 ms; max 3.32 ms. |
| Synthetic crowded-input benchmark | 360 decisions; 15 enemies + 32 projectiles; all three secondary weapon kinds exercised. |
| Crowded-input latency | Median 0.61 ms; p99 14.45 ms; max 17.90 ms; zero decisions above 50 ms. |
| Output serialization | Benchmark actions serialize with finite numbers and remain below the protocol line limit. |
| Docker base provenance | Official Python manifest digest retrieved; `linux/amd64` image present. |

Measured times naturally vary with the computer's load and CPU. In particular,
direct-call times exclude subprocess and protocol I/O. The official checker
includes those costs, but this Windows machine is not the match container.

The behavioral tests cover terrain interpolation, body size, map edges, walls,
courtyards, roof and bridge clearance, thin-wall collisions, routing around a
wall and out of a U-shaped dead end, live-stat aiming, projectile interception,
laser release timing, lightning limits, mortar ballistics, self-splash avoidance,
zone interpolation, defensive upgrades, vertical loot separation, recovery
behavior, and failure to start without a map.

## GitHub Actions Linux sandbox: PASS

The public repository is [Muallim718/oval-sentinel](https://github.com/Muallim718/oval-sentinel).
The [initial successful workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44911786415)
checked bot commit `68b9a63a0f676998df0642f1657b808ea3b26cd0` on Ubuntu 24.04.

- All 21 behavioral tests passed on Linux.
- Committed tree: 29 files, 2,075,149 bytes, below 20,000,000 bytes.
- The pinned `linux/amd64` Docker image built successfully.
- Restricted-container official checker: **300/300 on-time answers**, zero misses.
- Container startup: 625 ms; response latency p50 0.6 ms, p90 1.6 ms,
  p99 4.0 ms, maximum 5.5 ms.
- Container restrictions included no network, one CPU, 512 MB memory with no swap,
  uid 65534, no capabilities, 128-process limit, read-only root filesystem,
  read-only `/arena`, and a 64 MB `/tmp` tmpfs.
- The synthetic crowded-input benchmark on the Linux host reported p99 19.60 ms
  and maximum 23.81 ms, with zero decisions above 50 ms. That benchmark runs on
  the host; only the official stream was checked inside the restricted container.

## Not yet verified

- **Finalist performance and rebuild.** The first scored practice run completed,
  but no qualifier or final has been played. The kit replay is not a simulation
  and cannot measure placement or full-match route success.
- **Match-level diagnosis.** The event page showed an aggregate score; no win rate,
  per-match placements, or replay analysis was available in the submission summary.

## First scored practice submission

- Receipt: `BB-3FEACC8C`.
- Submitted: 2026-11-21, 9:12 AM EST, for team Mu.
- Commit: `d8e307a9dc89bf858edb40993daf15581a9afe2b` (verified by the
  [successful Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44911863761)).
- Status: **Scored**.
- Score: **1.50** placement points, +0.35 over the published 1.15 starter baseline.
- Implied average placement: approximately 14.50, from `16 - score`.
- Observed board position when read: 233 of 247 teams; this can change.
- The site marked it "Entered in the final (your best score)". This is the
  automatic current-entry selection, not confirmation of qualification.
- One hourly submission slot was consumed; three remained immediately afterward.

The result establishes a scored baseline. It does not establish competitive or
winning performance. The original submitted commit remains publicly available.

## Reproduce

From this folder on this Windows computer:

```powershell
py -3.13 tools/verify.py
```

With Docker running:

```powershell
py -3.13 tools/verify.py --docker
```

To create a clean source ZIP:

```powershell
py -3.13 tools/package.py
```

On Linux/macOS, replace `py -3.13` with `python3`.
