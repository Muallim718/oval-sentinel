# Oval Sentinel

A readable, survival-oriented bot for **Mech Royale**, using Python's standard
library only. The `Dockerfile` is already at the repository root.

[![Bot checks](https://github.com/Muallim718/oval-sentinel/actions/workflows/check.yml/badge.svg)](https://github.com/Muallim718/oval-sentinel/actions/workflows/check.yml)

Public repository: https://github.com/Muallim718/oval-sentinel

**Linux sandbox verified:** the initial published bot passed all 21 behavioral
tests and the official restricted-container check (300/300 on-time answers;
5.5 ms maximum response). See [VALIDATION.md](VALIDATION.md) for the run link.

**Start here:** run the tests, create a public GitHub repository from this folder,
wait for its Linux sandbox check to pass, then submit that repository's URL.

This is a complete implementation, not a demonstrated winning entry. The kit
contains a recorded protocol test, not a match simulator. No placement score or
win rate has been measured yet.

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

That runs behavioral tests, the official 300-observation conformance check, and
a crowded-input timing benchmark. It fails if a test or the official check fails.
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
| `sentinel/navigation.py` | A* routes around buildings; searches can continue across decisions. |
| `sentinel/geometry.py` | Terrain heights, walls, courtyards, bridges, and shot obstruction. |
| `sentinel/combat.py` | Bullet leading, mortar arcs, laser charging, and lightning checks. |
| `mechfight.py` | Kit transport wrapper; reads JSON lines and answers the newest observation. |
| `tests/test_bot.py` | Focused behavior regressions. |
| `tools/verify.py` | The single verification command. |
| `tools/benchmark.py` | Recorded and synthetic decision latency checks. |
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
creation if you are using that repository. No scored submission has been made yet.

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
