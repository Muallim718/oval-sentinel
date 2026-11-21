"""Audit policy decisions on the kit recording. Counts are not a match score.

Pass --project-dir PATH to audit an archived older version with the same tool.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_dir.resolve()
    sys.path.insert(0,str(root))
    from sentinel.strategy import Bot
    with gzip.open(root/"check/stream.jsonl.gz","rt",encoding="utf-8") as f:
        messages = [json.loads(line) for line in f]
    hello = next(m for m in messages if m["type"] == "hello")
    hello["map"]["dir"] = str(root/"arena")
    bot = Bot(hello)
    counts = Counter()
    for obs in (m for m in messages if m["type"] == "obs"):
        action = bot.act(obs)
        enemy = any(e["kind"] == "mech" for e in obs["mechs"])
        counts["observations"] += 1
        counts["enemy_visible"] += enemy
        counts["gun_trigger"] += action["fire"][0]
        counts["reload_commands"] += action.get("reload",False)
        counts["reload_with_enemy"] += enemy and action.get("reload",False)
        gun = next((w for w in obs["self"]["weapons"] if w and w["kind"] == "gun"),None)
        counts["partial_magazine_reload_with_enemy"] += bool(enemy and gun and gun.get("ammo",0) > 0 and action.get("reload",False))
    print(json.dumps(dict(counts),indent=2))


if __name__ == "__main__":
    main()
