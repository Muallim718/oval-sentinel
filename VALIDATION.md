# Validation performed

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
