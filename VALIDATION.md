# Validation performed

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

## Not yet verified

- **Docker image build and Linux sandbox execution.** Docker and WSL are absent
  from the preparation computer. Run `py -3.13 tools/verify.py --docker` with
  Docker installed, or push to GitHub and wait for the included Actions check.
- **Actual practice or final performance.** No scored matches have been run. The
  official kit provides a recording, not an interactive engine. It cannot measure
  wins, placement, route success over a full match, or an improvement over 1.15.
- **Finalist rebuild and event submission.** No repository has been published,
  no URL submitted, and no submission slot consumed.

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
