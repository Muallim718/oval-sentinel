"""Controlled gun/laser output model, not a match simulator or score predictor.

Target circles an unobstructed shooter at 120 m. Aim slews, gun magazines/reloads,
cooldowns, charge/release, and shots receive feedback using published config.
--project-dir audits an archived bot with this same model for an A/B comparison.
"""
import argparse
from collections import Counter
import copy
import gzip
import json
import math
from pathlib import Path
import sys


class OpenWorld:
    def ground(self,x,y):
        return 0.0

    def line_clear(self,a,b):
        return True


def simulate(combat,config,initial,seconds=30,separation=120,speed=12):
    me = copy.deepcopy(initial)
    me.update(pos=[0,0,0],vel=[0,0,0],aim=[0,0],hp=1400,max_hp=1400)
    gun = {"kind":"gun","cooldown":0,"ammo":config["weapons"]["gun"]["mag"],"reload":0,
           "stats":copy.deepcopy(config["weapons"]["gun"])}
    laser = {"kind":"laser","cooldown":0,"charge":0,"stats":copy.deepcopy(config["weapons"]["laser"])}
    me["weapons"] = [gun,laser]
    counts = Counter()
    dt,omega = .05,speed/separation

    def target(now):
        a = omega*now
        return {"id":1,"kind":"mech","pos":[separation*math.cos(a),separation*math.sin(a),0],
                "vel":[-speed*math.sin(a),speed*math.cos(a),0],"hp":1400,"max_hp":1400,"cubes":0}

    def shot_hit(kind,now):
        # Approximate travel time to the circular target; gun muzzle offset is
        # along the ray. There is no spread or cover in this controlled model.
        travel = (separation-3)/gun["stats"]["speed"] if kind == "gun" else 0
        p = target(now+travel)["pos"]
        yaw,pitch = me["aim"]
        direction = [math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)]
        along = p[0]*direction[0]+p[1]*direction[1]
        transverse = math.hypot(p[0]-direction[0]*along,p[1]-direction[1]*along)
        z = me["stats"]["muzzle_height"]+direction[2]*along
        return along > 0 and transverse <= config["mech"]["radius"]+.3 and 0 < z < config["mech"]["height"]

    for decision in range(round(seconds/.1)):
        now = decision*.1
        aim,fire,_ = combat.action(me,[target(now)],False,False)
        aim = aim or me["aim"]
        for substep in range(2):
            t = now+substep*dt
            yaw_error = (aim[0]-me["aim"][0]+math.pi)%math.tau-math.pi
            me["aim"][0] += max(-me["stats"]["turn_rate"]*dt,min(me["stats"]["turn_rate"]*dt,yaw_error))
            pitch_error = aim[1]-me["aim"][1]
            me["aim"][1] += max(-me["stats"]["pitch_rate"]*dt,min(me["stats"]["pitch_rate"]*dt,pitch_error))
            gun["cooldown"] = max(0,gun["cooldown"]-dt)
            laser["cooldown"] = max(0,laser["cooldown"]-dt)
            if gun["reload"] > 0:
                gun["reload"] = max(0,gun["reload"]-dt)
                if gun["reload"] == 0:
                    gun["ammo"] = gun["stats"]["mag"]
            if gun["ammo"] == 0 and gun["reload"] == 0:
                gun["reload"] = gun["stats"]["reload"]
            if fire[0] and gun["cooldown"] == 0 and gun["reload"] == 0 and gun["ammo"] > 0:
                counts["gun_shots"] += 1
                counts["gun_hits"] += shot_hit("gun",t)
                counts["gun_shots_during_charge"] += laser["charge"] > 0
                gun["ammo"] -= 1
                gun["cooldown"] = gun["stats"]["cooldown"]
            if laser["cooldown"] == 0:
                if fire[1]:
                    laser["charge"] += dt
                release = (laser["charge"] >= laser["stats"]["min_charge"] and not fire[1])
                forced = laser["charge"] >= laser["stats"]["charge"]+laser["stats"]["hold_s"]
                if release or forced:
                    fraction = min(1,laser["charge"]/laser["stats"]["charge"])
                    strength = laser["stats"]["min_frac"]+(1-laser["stats"]["min_frac"])*fraction
                    counts["laser_shots"] += 1
                    counts["full_charge_shots"] += fraction >= 1
                    counts["forced_laser_shots"] += forced
                    if shot_hit("laser",t):
                        counts["laser_hits"] += 1
                        counts["laser_damage"] += strength*laser["stats"]["damage"]
                    laser["charge"],laser["cooldown"] = 0,laser["stats"]["cooldown"]
    counts["gun_damage"] = counts["gun_hits"]*gun["stats"]["damage"]
    counts["total_damage"] = counts["gun_damage"]+counts["laser_damage"]
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--separation",type=float,default=120)
    parser.add_argument("--speed",type=float,default=12)
    parser.add_argument("--sweep",action="store_true")
    args = parser.parse_args()
    root = args.project_dir.resolve()
    sys.path.insert(0,str(root))
    from sentinel.combat import Combat
    with gzip.open(root/"check/stream.jsonl.gz","rt",encoding="utf-8") as f:
        hello = json.loads(next(f))
        initial = json.loads(next(f))["self"]
    if args.sweep:
        results = []
        for separation in (60,120,190):
            for speed in (0,6,12):
                result = simulate(Combat(OpenWorld(),hello["config"]),hello["config"],initial,
                                  separation=separation,speed=speed)
                results.append({"range":separation,"speed":speed,**result})
        print(json.dumps(results,indent=2))
    else:
        combat = Combat(OpenWorld(),hello["config"])
        print(json.dumps(simulate(combat,hello["config"],initial,separation=args.separation,speed=args.speed),indent=2))


if __name__ == "__main__":
    main()
