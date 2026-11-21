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

- **Actual practice or final performance.** No scored matches have been run. The
  official kit provides a recording, not an interactive engine. It cannot measure
  wins, placement, route success over a full match, or an improvement over 1.15.
- **Finalist rebuild and event submission.** The repository is public, but no URL
  has yet been submitted and no submission slot has been consumed.

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
