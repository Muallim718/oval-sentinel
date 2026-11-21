"""Cold bots at quiet public-map positions; exercises proactive roof search."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import statistics
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--count", type=int, default=40)
    args = parser.parse_args()
    root = args.project_dir.resolve()
    sys.path.insert(0, str(root))
    from sentinel.geometry import World, distance
    from sentinel.strategy import Bot
    with gzip.open(root/"check/stream.jsonl.gz", "rt", encoding="utf-8") as stream:
        hello, initial = json.loads(next(stream)), json.loads(next(stream))
    hello["map"]["dir"] = str(root/"arena")
    world = World(hello["map"]["dir"])
    bounds, stats = world.bounds, initial["self"]["stats"]
    points = []
    for y in range(int(bounds["minY"])+12, int(bounds["maxY"])-12, 24):
        for x in range(int(bounds["minX"])+12, int(bounds["maxX"])-12, 24):
            z = world.ground(x, y)
            if (distance((x, y), initial["zone"]["center"]) < 490 and
                    world.body_clear(x, y, z, stats["radius"]+.5, stats["height"])):
                points.append((x, y, z))
    count = max(1, min(args.count, len(points)))
    if not points:
        raise RuntimeError("no valid public-map timing positions")
    positions = [points[round(i*(len(points)-1)/max(1, count-1))] for i in range(count)]
    decisions, startups, plans = [], [], 0
    for position in positions:
        obs = copy.deepcopy(initial)
        obs.update(t=0, tick=0, events=[], mechs=[], projectiles=[], cubes=[],
                   pickups=[], crates=[], drops=[], offer=None)
        me = obs["self"]
        me.update(pos=list(position), vel=[0, 0, 0], hp=me["max_hp"],
                  energy=me["max_energy"], cubes=0, grounded=True, in_zone=True)
        start = time.perf_counter()
        bot = Bot(copy.deepcopy(hello))
        startups.append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        action = bot.act(obs)
        decisions.append((time.perf_counter()-start)*1000)
        json.dumps(action, allow_nan=False)
        assert action["tick"] == obs["tick"]
        altitude = getattr(bot, "altitude", None)
        plans += bool(altitude and altitude.active)
    print(f"quiet public-map starts (synthetic): {count} fresh bots; "
          f"startup max {max(startups):.1f} ms; decision median {statistics.median(decisions):.2f} ms; "
          f"max {max(decisions):.2f} ms; >50 ms {sum(t > 50 for t in decisions)}; roof plans {plans}")


if __name__ == "__main__":
    main()
