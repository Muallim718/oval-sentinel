"""Count mission/posture choices on fixed kit observations, not match outcomes."""
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
    choices = Counter()
    counts = Counter(observations=0, recorded_gun_only=0, weapon_goals=0,
                     gun_only_fight_against_secondary=0)
    for obs in (m for m in messages if m["type"] == "obs"):
        bot.act(obs)
        unarmed = obs["self"]["weapons"][1] is None
        counts["observations"] += 1
        counts["recorded_gun_only"] += unarmed
        counts["weapon_goals"] += bot.goal_kind == "weapon"
        counts["gun_only_fight_against_secondary"] += bool(
            unarmed and bot.mode == "fight" and bot.duel and
            any(kind != "gun" for kind in bot.duel.get("weapons", [])))
        choices[f"{bot.mode}/{bot.goal_kind}"] += 1
    print(json.dumps({**counts, "mode_and_goal": dict(sorted(choices.items()))}, indent=2))


if __name__ == "__main__":
    main()
