"""Replay and synthetic latency checks. This does NOT simulate a match or score."""
import copy
import gzip
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentinel.strategy import Bot


def load_stream():
    with gzip.open(ROOT/"check/stream.jsonl.gz", "rt", encoding="utf-8") as f:
        messages = [json.loads(line) for line in f]
    hello = next(m for m in messages if m["type"] == "hello")
    hello["map"]["dir"] = str(ROOT/"arena")
    return hello, [m for m in messages if m["type"] == "obs"]


def benchmark(label, hello, observations):
    start = time.perf_counter()
    bot = Bot(hello)
    startup = (time.perf_counter()-start)*1000
    times = []
    for obs in observations:
        start = time.perf_counter()
        action = bot.act(obs)
        times.append((time.perf_counter()-start)*1000)
        # Detect NaN/Infinity and oversized messages, which the loose schema
        # validator alone will not necessarily catch.
        encoded = json.dumps(action, allow_nan=False)
        assert len(encoded.encode()) <= hello["config"]["bot"]["max_line_bytes"]
        assert action["tick"] == obs["tick"]
    ordered = sorted(times)
    print(f"{label}: startup {startup:.1f} ms; decisions {len(times)}; "
          f"median {statistics.median(times):.2f} ms; "
          f"p99 {ordered[min(len(ordered)-1,int(len(ordered)*.99))]:.2f} ms; "
          f"max {max(times):.2f} ms; >50 ms {sum(t>50 for t in times)}")
    return times


def crowded(hello, initial, count=360):
    """Adversarial input load, not an opponent model or a valid game trajectory."""
    import math
    from sentinel.geometry import World
    world = World(hello["map"]["dir"])
    for tick in range(count):
        obs = copy.deepcopy(initial)
        obs["tick"], obs["t"] = tick*2, tick/10+160
        obs["zone"].update(center=[150, -60], radius=240, next_center=[40,20],
                           next_radius=140, shrink_start=170, shrink_end=205)
        me = obs["self"]
        me["pos"] = [150+math.sin(tick/25)*8, -60, 0]
        me["pos"][2] = world.ground(*me["pos"][:2])
        assert world.body_clear(*me["pos"])
        me["hp"] = 700 if tick % 60 < 30 else 1400
        kind = ("laser", "mortar", "lightning")[(tick//60)%3]
        me["weapons"][1] = {"kind":kind, "cooldown":0, "charge":(tick%10)/10 if kind == "laser" else 0,
                              "stats":hello["config"]["weapons"][kind]}
        obs["mechs"] = []
        for i in range(15):
            a = i*math.tau/15+tick/90
            d = 25+i*10
            ep = [150+d*math.cos(a), -60+d*math.sin(a), 0]
            ep[2] = world.ground(*ep[:2])
            obs["mechs"].append({"id":i if i < 3 else i+1, "kind":"mech", "pos":ep,
                                 "vel":[-math.sin(a)*12, math.cos(a)*12,0], "aim":[a+math.pi,0],
                                 "hp":1000, "max_hp":1400, "weapons":["gun","laser"],
                                 "charging":True, "cubes":0})
        obs["projectiles"] = [{"id":2000+i,"kind":"gun","pos":[me["pos"][0]+i+10,-60+i,me["pos"][2]+7],
                                 "vel":[-180,-40,0]} for i in range(32)]
        yield obs


def growing(hello, initial):
    """Stress route cache invalidation with six cube/body sizes."""
    for i,obs in enumerate(crowded(hello,initial,count=180)):
        cubes = i//30
        obs["self"]["cubes"] = cubes
        scale = 1+hello["config"]["cubes"].get("size_per_cube",.05)*cubes
        for key in ("radius","height","eye_height","muzzle_height"):
            obs["self"]["stats"][key] = hello["config"]["mech"][key]*scale
        yield obs


if __name__ == "__main__":
    hello, observations = load_stream()
    benchmark("official recording (direct calls)", hello, observations)
    benchmark("15 enemies + 32 projectiles (synthetic)", hello, crowded(hello, observations[0]))
    benchmark("growing body + crowded inputs (synthetic)", hello, growing(hello,observations[0]))
