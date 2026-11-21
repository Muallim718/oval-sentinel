# Validation performed

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
