"""Audit recovery decisions on the kit stream; this does not predict placement."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_dir.resolve()
    sys.path.insert(0, str(root))
    from sentinel.strategy import Bot
    with gzip.open(root/"check/stream.jsonl.gz", "rt", encoding="utf-8") as stream:
        messages = [json.loads(line) for line in stream]
    hello = next(m for m in messages if m["type"] == "hello")
    hello["map"]["dir"] = str(root/"arena")
    bot = Bot(hello)
    counts = Counter(observations=0, recovery_observations=0,
                     recovery_gun_trigger=0, recovery_recent_weapon_damage=0)
    last_weapon_damage = -100
    for obs in (m for m in messages if m["type"] == "obs"):
        if any(e["type"] == "damaged" and e.get("weapon") not in (None, "zone")
               for e in obs["events"]):
            last_weapon_damage = obs["t"]
        action = bot.act(obs)
        counts["observations"] += 1
        if bot.recovering and bot.mode != "fight":
            counts["recovery_observations"] += 1
            gun_slot = next((i for i, w in enumerate(obs["self"]["weapons"])
                             if w and w["kind"] == "gun"), None)
            counts["recovery_gun_trigger"] += gun_slot is not None and action["fire"][gun_slot]
            counts["recovery_recent_weapon_damage"] += obs["t"]-last_weapon_damage < 1.0
    print(json.dumps(dict(counts), indent=2))


if __name__ == "__main__":
    main()
