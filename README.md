# Oval Sentinel

A readable, survival-oriented bot for **Mech Royale**, using Python's standard
library only. The `Dockerfile` is already at the repository root.

[![Bot checks](https://github.com/Muallim718/oval-sentinel/actions/workflows/check.yml/badge.svg)](https://github.com/Muallim718/oval-sentinel/actions/workflows/check.yml)

Public repository: [Muallim718/oval-sentinel](https://github.com/Muallim718/oval-sentinel)

**Best scored entry is 4.04 placement points.** This version follows through
in isolated early duels while preserving cover, kill rewards, and the power
opener. Receipt `BB-5EE1F65A` scored commit
`47a4d7d56a20a274dd8c38f946c8456fc9fa8176` on 2026-11-21 at 4:00 PM EST.
The site selected it automatically. The `score-4.04` tag preserves the exact
submission. [Duel design and practice result](docs/REVISION_20.md)

| Version | Change | Practice score |
| --- | --- | ---: |
| [7](docs/REVISION_7.md) | Recovery self-defense baseline | 3.25 |
| [8](docs/REVISION_8.md) | Committed cover and predictive steering | **3.63** |
| [9](docs/REVISION_9.md) | Readiness and protected resource acquisition | 3.58 |
| [10](docs/REVISION_10.md) | Proactive rooftop sanctuary | 3.40 |
| [11](docs/REVISION_11.md) | Stay on safe roof space through zone movement | 3.31 |
| [12](docs/REVISION_12.md) | Incoming-shot prediction, spacing, and firing windows | 3.38 |
| [13](docs/REVISION_13.md) | Collect confirmed kill rewards before the next hunter | **3.73** |
| [14](docs/REVISION_14.md) | Finish weakened opponents within the incoming damage budget | 3.58 |
| [15](docs/REVISION_15.md) | Prepare laser shots behind cover and return after release | 3.58 |
| [16](docs/REVISION_16.md) | Acquire early weapons and cubes through dedicated missions | **3.75** |
| [17](docs/REVISION_17.md) | Acquire contacts through sound and aim at exposed surfaces | 3.96 |
| [20](docs/REVISION_20.md) | Sustain isolated duels through the first waves | **4.04** |
| [23](docs/REVISION_23.md) | Repair and rearm during the gap after a kill | 4.00 |

**The default runtime matches the 4.04 controller.** The exact source and
tests for earlier revisions remain public in their tags and experiment branches.

**Linux sandbox verified.** Revision 20 passed 125 tests. The official
restricted-container check received 300/300 on-time replies, with a 14.9 ms
maximum response. [Validation and experimental results](VALIDATION.md)

**Start here:** run the checks below, read [the strategy](docs/STRATEGY.md), and
consult the [full submission history](docs/PRACTICE_LOG.csv). Experiments that
scored lower are archived publicly; they do not replace the selected best entry.

## 1. Test it

Python 3.11 or newer is sufficient locally; the image pins Python 3.13.9.
There are **no packages to install**.

**On this Windows computer**, open a terminal in this folder and run:

```powershell
py -3.13 tools/verify.py
```

**On macOS/Linux:**

```sh
python3 tools/verify.py
```

That runs behavioral tests, the official 300-observation conformance check,
and crowded-input timing. It fails if a test or the official check fails.
The benchmark reports timing; its synthetic inputs are not scored games.

**With Docker running**, add `--docker` to build for `linux/amd64` and run the
official checker with the match restrictions:

```sh
python3 tools/verify.py --docker
```

On Windows, use `py -3.13` instead of `python3`.

Docker is not installed on the computer where this project was prepared. The
container build and Linux sandbox check were successfully executed on Ubuntu
through GitHub Actions. The workflow repeats them when you push.
See [VALIDATION.md](VALIDATION.md) for the checks actually run.

## 2. Understand the bot

Think of each decision as five questions:

1. **Will the zone reach me soon?** Predict the moving circle and rotate early.
2. **Am I exposed or hurt?** Find a safer position, use cover, and preserve energy.
3. **Can I collect something safely?** Prefer accessible cubes, useful weapons,
   nearby crates, and uncontested supply drops.
4. **Can I hit a worthwhile target?** Lead bullets, respect buildings and range,
   and wait for the actual torso aim before firing.
5. **Which upgrade helps me survive?** Prefer movement, regeneration, and armor.

| File | What you will find |
| --- | --- |
| `bot.py` | Tiny entry point. |
| `sentinel/strategy.py` | Those five decisions; read this first. |
| `sentinel/tuning.py` | Strategy preferences and upgrade priorities. |
| `sentinel/memory.py` | Previously observed loot and stale-item removal. |
| `sentinel/cover.py` | Wall-side shelters, body-wide firing lanes, commitment, and rejection. |
| `sentinel/movement.py` | Acceleration-aware command rollouts, braking, exposure, and dodging. |
| `sentinel/navigation.py` | A* routes around buildings; searches can continue across decisions. |
| `sentinel/geometry.py` | Terrain heights, walls, courtyards, bridges, and shot obstruction. |
| `sentinel/combat.py` | Bullet leading, mortar arcs, laser charging, and lightning checks. |
| `mechfight.py` | Kit transport wrapper; reads JSON lines and answers the newest observation. |
| `tests/test_bot.py` | Focused behavior regressions. |
| `tools/verify.py` | The single verification command. |
| `tools/benchmark.py` | Recorded and synthetic decision latency checks. |
| `tools/diagnose.py` | Policy-output audit of the kit recording. |
| `tools/audit_missions.py` | Compare arming missions and combat posture on the fixed recording. |
| `tools/ground_lab.py` | Optional reactive gun stress model; not the server or a score predictor. |
| `docs/protocol.md` | Official rules and message specification. |

Read [docs/STRATEGY.md](docs/STRATEGY.md) for the reasoning and tradeoffs.

## 3. Publish and submit

Keep this folder's contents at the **root** of a new public GitHub repository.
Do not upload the enclosing ZIP as the repository's only file.

With Git and GitHub CLI installed and signed in, these commands create a public
repository. Replace `YOUR-USERNAME` with your GitHub username and choose a unique
repository name if `oval-sentinel` is already taken:

```sh
git init -b main
git add .
git commit -m "Build Oval Sentinel survival bot"
gh repo create YOUR-USERNAME/oval-sentinel --public --source . --remote origin --push
```

This project is already published at `Muallim718/oval-sentinel`; skip repository
creation if you are using that repository. The initial scored submission is
recorded in `docs/PRACTICE_LOG.csv`; submitting again consumes another hourly slot.

In GitHub's **Actions** tab, wait for **Bot checks / linux-sandbox** to pass.
It builds the pinned image and checks no-network execution, uid 65534, one CPU,
512 MB RAM, a read-only filesystem, and the mounted map.

Then open the [Mech Royale submission page](https://www.joinbuilders.org/buildathon/tracks/builders)
and submit your public repository URL. The supplied event rules allow four
submissions per hour; each practice submission plays 48 matches. The stated
cutoff is Sunday at 11:00 AM EST. Keep every submitted commit publicly available
until results are published.

Before submitting, `python3 tools/package.py` checks the working-tree size and
creates a clean ZIP outside the repository. GitHub Actions also checks the size
of the actual committed tree against the 20 MB limit.

## 4. Improve using real results

Record the commit, practice score, and observed failures in
[docs/PRACTICE_LOG.csv](docs/PRACTICE_LOG.csv). Placement points are
`mean(16 - place)`; kills alone do not establish a better bot.

Start with this version as a control. Change one preference at a time in
`sentinel/tuning.py`, rerun verification, and compare practice scores. The
practice opponents cooperate as a squad, while qualifiers and finals are
free-for-alls; do not assume an aggressive practice improvement transfers to the
final. Earlier submissions win score ties, so establish a valid submission early.

## Optional debug drawings

Set `BOT_DEBUG=1` to attach a short state label and goal marker to actions. Debug
drawings are capped and have no gameplay effect. The official rules say the
event UI does not show these drawings; they are only for your own tooling.

```powershell
$env:BOT_DEBUG = '1'
py -3.13 check/check.py -- py -3.13 -u bot.py
Remove-Item Env:BOT_DEBUG
```

## Runtime and reproducibility

- Python 3.13.9 base image is pinned by immutable Docker manifest digest.
- No downloads, third-party dependencies, model calls, or network use at runtime.
- No runtime file writes; map is read only. Bytecode writes are disabled.
- Physics and weapon numbers come from `hello.config` and live upgraded stats.
- The seed only chooses our scan/route phase; it is never treated as a match seed.
- Search work has expansion and wall-time limits, leaving decision-budget margin.
  The wall-time bound can produce slightly different partial routes on different
  CPUs. This is a practical latency safeguard, not exact cross-machine determinism.

See [SOURCES.md](SOURCES.md) for kit provenance and modifications.
