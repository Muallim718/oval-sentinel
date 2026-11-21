"""20Hz acquisition and weapon clocks; component evidence, not placement claims.

Movement uses public acceleration/energy and body collision. Shots use actual
torso, forward barrel, continuous moving-cylinder gun collisions and real laser
charge/cooldown/half-speed movement. Both unknown turn/fire orders are tested.
The stationary enemy does not return fire: this isolates acquisition and output.
"""
import copy
import json
import math
import os
from pathlib import Path
import random
import sys
import unittest

SOURCE = Path(os.environ.get("LASER_TEST_SOURCE", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE/"tests"))
sys.path.insert(0, str(SOURCE/"tools"))
from test_bot import fixture, flat_world
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.geometry import angle_error, distance
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.opener import Opener
from sentinel.salvage import KillSalvage
from sentinel.strategy import Bot
from ground_lab import cylinder_entry

DT = .05


def move(me, action, world, charging=False):
    stats = me["stats"]
    command = action.get("move", [0, 0])
    length = max(1, math.hypot(*command))
    boost = action.get("boost", False) and me["energy"] >= stats["boost_drain"]*DT
    speed = stats["boost_speed"] if boost else stats["walk_speed"]
    if charging:
        speed *= stats["charge_move_mult"]
    wanted = [command[i]/length*speed for i in range(2)]
    delta = [wanted[i]-me["vel"][i] for i in range(2)]
    norm = math.hypot(*delta)
    fraction = min(1, stats["ground_accel"]*DT/max(1e-12, norm))
    me["vel"] = [me["vel"][i]+delta[i]*fraction for i in range(2)]+[0]
    proposed = [me["pos"][i]+me["vel"][i]*DT for i in range(3)]
    clear = world.walk_clear(me["pos"], proposed, stats["radius"], stats["height"], stats["step_up"])
    if clear:
        me["pos"] = proposed
    else:
        me["vel"] = [0, 0, 0]
    if boost and math.hypot(*command) > 0:
        me["energy"] -= stats["boost_drain"]*DT
        me["_quiet"] = 0
    else:
        me["_quiet"] = me.get("_quiet", 100)+DT
        if me["_quiet"] >= stats["energy_regen_delay"]:
            me["energy"] = min(stats["energy"], me["energy"]+stats["energy_regen"]*DT)
    return clear


def acquisition():
    hello, obs = fixture()
    bot, world = Bot(hello), flat_world()
    config = hello["config"]
    bot.world = world
    bot.nav = Navigator(world, config["mech"])
    bot.combat = Combat(world, config)
    bot.cover = CoverPlanner(world, config)
    bot.motion = GroundSteering(world, config)
    bot.opener = Opener(world, config)
    bot.salvage = KillSalvage(world, config)
    if hasattr(bot, "laser_doctrine"):
        from sentinel.laser_doctrine import LaserDoctrine
        bot.laser_doctrine = LaserDoctrine(world, config)
    me = obs["self"]
    me.update(pos=[-70, 0, 0], vel=[0, 0, 0], aim=[0, 0], hp=1400, max_hp=1400,
              energy=100, cubes=0, grounded=True, in_zone=True)
    me["weapons"][0].update(ammo=12, reload=0, cooldown=0)
    me["weapons"][1] = dict(kind="lightning", cooldown=0,
                            stats=copy.deepcopy(config["weapons"]["lightning"]))
    item = dict(id=8001, kind="laser", pos=[20, 0, 0])
    obs.update(alive=16, events=[], mechs=[], projectiles=[], crates=[], cubes=[],
               drops=[], pickups=[item], offer=None)
    obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0], next_radius=118,
                       shrink_start=500, shrink_end=550)
    action, minimum_energy, shots, collided = {}, 100, 0, False
    for tick in range(160):
        # After the original opener ends; the held arc is the actual obstacle.
        obs.update(t=75+tick*DT, tick=1500+tick)
        if tick % 2 == 0:
            action = bot.act(copy.deepcopy(obs))
        collided |= not move(me, action, world)
        minimum_energy = min(minimum_energy, me["energy"])
        shots += sum(bool(value) for value in action["fire"])
        if action.get("take") == item["id"]:
            replacing = action.get("drop")
            if (distance(me["pos"], item["pos"]) <= config["loot"]["pickup_radius"] and
                    abs(me["pos"][2]-item["pos"][2]) <= 4 and replacing == 1):
                stats = copy.deepcopy(config["weapons"]["laser"])
                me["weapons"][1] = dict(kind="laser", charge=0,
                    cooldown=max(config["loot"]["equip_s"], stats["cooldown"]), stats=stats)
                return dict(acquired_s=round(tick*DT, 4), gun_retained=me["weapons"][0]["kind"] == "gun",
                            minimum_energy=minimum_energy, fired_commands=shots, collided=collided,
                            equip_cooldown=me["weapons"][1]["cooldown"])
    return dict(acquired_s=None, gun_retained=me["weapons"][0]["kind"] == "gun",
                minimum_energy=minimum_energy, fired_commands=shots, collided=collided)


def kit_output(kind, before_turn=False, seconds=8):
    hello, obs = fixture()
    config, world = hello["config"], flat_world()
    me = copy.deepcopy(obs["self"])
    me.update(pos=[-40, -40, 0], vel=[0, 0, 0], aim=[0, -.025], energy=100, cubes=0)
    gun = me["weapons"][0]
    gun.update(ammo=12, reload=0, cooldown=0)
    second = dict(kind=kind, charge=0, cooldown=0, stats=copy.deepcopy(config["weapons"][kind]))
    me["weapons"][1] = second
    enemy = dict(id=1, kind="mech", pos=[60, -40, 0], vel=[0, 7, 0], hp=10000,
                 max_hp=10000, cubes=0, aim=[math.pi, 0], weapons=["gun"])
    combat, rng = Combat(world, config), random.Random(29)
    action, flying, damage, beams, gun_hits = {}, [], 0, [], 0
    charged_s, fast_s, charged_speed, fast_speed, collision = 0, 0, 0, 0, False

    def turn():
        aim = action["aim"]
        me["aim"][0] += max(-me["stats"]["turn_rate"]*DT,
            min(me["stats"]["turn_rate"]*DT, angle_error(aim[0], me["aim"][0])))
        me["aim"][1] += max(-me["stats"]["pitch_rate"]*DT,
            min(me["stats"]["pitch_rate"]*DT, aim[1]-me["aim"][1]))

    def ray(aim, maximum):
        yaw, pitch = aim
        direction = [math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)]
        muzzle = [me["pos"][0], me["pos"][1], me["pos"][2]+me["stats"]["muzzle_height"]]
        origin = [muzzle[i]+direction[i]*(me["stats"]["radius"]+.5) for i in range(3)]
        end = [origin[i]+direction[i]*maximum for i in range(3)]
        return muzzle, origin, end, direction

    for tick in range(round(seconds/DT)):
        now = tick*DT
        for weapon in me["weapons"]:
            weapon["cooldown"] = max(0, weapon.get("cooldown", 0)-DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0, gun["reload"]-DT)
            if gun["reload"] <= 1e-9:
                gun["reload"], gun["ammo"] = 0, gun["stats"]["mag"]
        if tick % 2 == 0:
            aim, fire, target = combat.action(me, [enemy], False, False)
            action = dict(aim=aim or me["aim"], fire=fire, move=[0, 1], boost=False)
            if gun["ammo"] == 0 and gun["reload"] == 0:
                gun["reload"] = gun["stats"]["reload"]
        charging = kind == "laser" and (second["charge"] > 0 or
                    (second["cooldown"] <= 0 and action["fire"][1]))
        collision |= not move(me, action, world, charging)
        if charging:
            charged_s += DT
            charged_speed += math.hypot(*me["vel"][:2])*DT
        else:
            fast_s += DT
            fast_speed += math.hypot(*me["vel"][:2])*DT
        if not before_turn:
            turn()
        if action["fire"][0] and gun["ammo"] > 0 and gun["reload"] == 0 and gun["cooldown"] <= 1e-9:
            spread = math.radians(gun["stats"]["spread_deg"])
            aim = [me["aim"][i]+rng.gauss(0, spread) for i in range(2)]
            muzzle, origin, _, direction = ray(aim, gun["stats"]["range"])
            if world.line_clear(muzzle, origin):
                flying.append(dict(pos=origin, vel=[v*gun["stats"]["speed"] for v in direction],
                                   remaining=gun["stats"]["range"]))
            gun["ammo"] -= 1
            gun["cooldown"] = gun["stats"]["cooldown"]
        if kind == "laser":
            held = second.get("_held", 0)
            trigger = action["fire"][1]
            if held > 0 and not trigger:
                second["_pending"] = True
            if held > 0 or (trigger and second["cooldown"] <= 0):
                held += DT
                second["_held"], second["charge"] = held, min(held, second["stats"]["charge"])
                stats = second["stats"]
                release = ((second.get("_pending") and held+1e-9 >= stats["min_charge"]) or
                           held+1e-9 >= stats["charge"]+stats["hold_s"])
                if release:
                    muzzle, origin, end, _ = ray(me["aim"], stats["range"])
                    entry = cylinder_entry(origin, end, enemy["pos"], 2.5, 9)
                    hit = entry is not None and world.line_clear(muzzle, origin)
                    if hit:
                        point = [origin[i]+(end[i]-origin[i])*entry for i in range(3)]
                        hit = world.line_clear(origin, point)
                    amount = stats["damage"]*(stats["min_frac"]+(1-stats["min_frac"])*min(1, held/stats["charge"]))
                    damage += amount if hit else 0
                    beams.append(dict(t=now, charge=held, hit=hit, damage=amount if hit else 0))
                    second.update(charge=0, _held=0, _pending=False, cooldown=stats["cooldown"])
        if before_turn:
            turn()
        target_next = [enemy["pos"][i]+enemy["vel"][i]*DT for i in range(3)]
        live = []
        for bullet in flying:
            a = bullet["pos"]
            b = [a[i]+bullet["vel"][i]*DT for i in range(3)]
            # Relative segment gives a continuous moving-body collision.
            relative_a = [a[i]-enemy["pos"][i] for i in range(3)]
            relative_b = [b[i]-target_next[i] for i in range(3)]
            entry = cylinder_entry(relative_a, relative_b, [0, 0, 0], 2.5, 9)
            hit = entry is not None
            if hit:
                point = [a[i]+(b[i]-a[i])*entry for i in range(3)]
                hit = world.line_clear(a, point)
            if hit:
                damage += gun["stats"]["damage"]
                gun_hits += 1
            else:
                bullet["remaining"] -= math.dist(a, b)
                if bullet["remaining"] > 0 and world.line_clear(a, b):
                    bullet["pos"] = b
                    live.append(bullet)
        flying = live
        enemy["pos"] = target_next
    return dict(damage=damage, beams=beams, gun_hits=gun_hits, charged_s=charged_s,
                charged_mean_speed=charged_speed/max(DT, charged_s),
                uncharged_mean_speed=fast_speed/max(DT, fast_s), collided=collision)


class LaserFeedbackTests(unittest.TestCase):
    def test_held_arc_becomes_laser_through_actual_acceleration_and_explicit_swap(self):
        result = acquisition()
        self.assertIsNotNone(result["acquired_s"], result)
        self.assertLess(result["acquired_s"], 8)
        self.assertTrue(result["gun_retained"])
        self.assertGreaterEqual(result["minimum_energy"], 26)
        self.assertFalse(result["collided"])
        self.assertEqual(result["fired_commands"], 0)
        self.assertEqual(result["equip_cooldown"], 1.65)

    def test_real_laser_charge_movement_and_cooldown_deliver_damage_outside_arc_range(self):
        for before_turn in (False, True):
            with self.subTest(before_turn=before_turn):
                laser = kit_output("laser", before_turn)
                arc = kit_output("lightning", before_turn)
                self.assertGreaterEqual(sum(b["hit"] for b in laser["beams"]), 2, laser)
                self.assertGreater(laser["damage"], arc["damage"]+200, (laser, arc))
                self.assertGreater(laser["charged_s"], 1.4)
                self.assertLess(laser["charged_mean_speed"], laser["uncharged_mean_speed"]*.7)
                self.assertFalse(laser["collided"])
                for previous, current in zip(laser["beams"], laser["beams"][1:]):
                    self.assertGreaterEqual(current["t"]-previous["t"], 2.35)


if __name__ == "__main__":
    if "--measure" in sys.argv:
        print(json.dumps(dict(acquisition=acquisition(), kits={str(order): {
            kind: kit_output(kind, order) for kind in ("laser", "lightning")}
            for order in (False, True)}), indent=2))
    else:
        unittest.main()
