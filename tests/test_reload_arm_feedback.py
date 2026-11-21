"""Reactive pickup/equip/secondary feedback; not the official simulator.

Runs the real Bot at10Hz inside the existing20Hz ground/gun model. Added laser
and lightning emissions use actual torso, range, collision and published clocks.
The paired CLI accepts an untouched baseline project, avoiding mocked policies.
"""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
if len(sys.argv) > 2 and sys.argv[1] == "--simulate":
    PROJECT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT/"tools"))
from ground_lab import Lab, DT, cylinder_entry, wrapped
from sentinel.combat import Combat
from sentinel.navigation import Navigator
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.opener import Opener


class ArmFeedback(Lab):
    def __init__(self, root=PROJECT, seed=11, kind="laser", seconds=16):
        super().__init__(root, "open_pursuit", seed, seconds)
        self.kind = kind
        self.me = self.entity(0, [0, 0, 0], 1000)
        self.enemy = self.entity(1, [80, 0, 0], 1000)
        self.enemies, self.entities = [self.enemy], [self.me, self.enemy]
        for entity in self.entities:
            entity["_combat"], entity["_spent"] = 29.5, 29.5
            entity["weapons"][0].update(ammo=0, reload=2.4, cooldown=0)
        self.me["aim"] = [0, math.atan2(-2.5, 80)]
        self.enemy["aim"] = [math.pi, math.atan2(-2.5, 80)]
        self.pickups = [{"id": 8001, "kind": kind, "pos": [-10, 0, 0]}]
        self.bot.world = self.world
        self.bot.nav = Navigator(self.world, self.config["mech"])
        self.bot.combat = Combat(self.world, self.config)
        self.bot.cover = CoverPlanner(self.world, self.config)
        self.bot.motion = GroundSteering(self.world, self.config)
        self.bot.opener = Opener(self.world, self.config)
        if hasattr(self.bot, "reload_arm"):
            from sentinel.reload_arm import ReloadArm
            self.bot.reload_arm = ReloadArm(self.world, self.config)
        self.enemy_nav = {1: Navigator(self.world, self.config["mech"])}
        self.enemy_waypoints = {}
        self.t = 30
        self.acquired_at = self.equip_ready_at = self.kill_at = None
        self.first_secondary = None
        self.secondary_shots, self.secondary_hits, self.secondary_damage = 0, 0, 0.
        self.effective_gun_hits = 0
        self.trace = []

    def observation(self, tick):
        obs = super().observation(tick)
        obs["alive"] = 16
        obs["pickups"] = [copy.deepcopy(p) for p in self.pickups
                          if self.visible(self.me, [*p["pos"][:2], p["pos"][2]+1])]
        return obs

    def move_entity(self, entity, action):
        laser = next((w for w in entity["weapons"] if w and w["kind"] == "laser"), None)
        charging = bool(laser and (laser.get("charge", 0) > 0 or laser.get("_held", 0) > 0 or
                                  laser.get("cooldown", 0) <= 0 and action.get("fire", [False, False])[1]))
        original = entity["stats"]
        if charging:
            entity["stats"] = dict(original)
            entity["stats"]["walk_speed"] *= original.get("charge_move_mult", .5)
            entity["stats"]["boost_speed"] *= original.get("charge_move_mult", .5)
        super().move_entity(entity, action)
        entity["stats"] = original

    def secondary_hit(self, owner, target, weapon, amount):
        bearing = math.atan2(owner["pos"][1]-target["pos"][1], owner["pos"][0]-target["pos"][0])
        rear = abs(wrapped(bearing-target["aim"][0])) > math.pi/2
        amount *= (target["stats"]["rear_mult"] if rear else 1)*(1-target["stats"].get("armor", 0))
        target["hp"] -= amount
        target["_combat"] = owner["_combat"] = self.t
        if owner["id"] == 0:
            self.secondary_hits += 1
            self.secondary_damage += amount
            self.metrics["damage_dealt"] += amount
            self.events.append(dict(type="hit", target=target["id"], weapon=weapon, amount=amount, rear=rear))
            if target["hp"] <= 0:
                self.metrics["kills"] += 1
                self.events.append(dict(type="kill", target=target["id"]))

    def release_laser(self, entity, weapon, held):
        stats, (yaw, pitch) = weapon["stats"], entity["aim"]
        origin = [*entity["pos"][:2], entity["pos"][2]+entity["stats"]["muzzle_height"]]
        end = [origin[0]+stats["range"]*math.cos(yaw)*math.cos(pitch),
               origin[1]+stats["range"]*math.sin(yaw)*math.cos(pitch), origin[2]+stats["range"]*math.sin(pitch)]
        hits = []
        for target in self.entities:
            if target is entity or target["hp"] <= 0:
                continue
            at = cylinder_entry(origin, end, target["pos"], target["stats"]["radius"], target["stats"]["height"])
            if at is not None:
                hits.append((at, target))
        for at, target in sorted(hits, key=lambda item: item[0]):
            point = [origin[i]+(end[i]-origin[i])*at for i in range(3)]
            if self.world.line_clear(origin, point):
                fraction = stats["min_frac"]+(1-stats["min_frac"])*min(1, held/stats["charge"])
                self.secondary_hit(entity, target, "laser", stats["damage"]*fraction)
            break
        if entity["id"] == 0:
            self.secondary_shots += 1
            if self.first_secondary is None:
                self.first_secondary = self.t
        weapon.update(charge=0, cooldown=stats["cooldown"], _held=0, _pending=False)

    def weapon(self, entity, action):
        super().weapon(entity, action)
        second = entity["weapons"][1]
        if second is None:
            return
        second["cooldown"] = max(0, second.get("cooldown", 0)-DT)
        trigger = bool(action.get("fire", [False, False])[1])
        stats = second["stats"]
        if second["kind"] == "laser":
            held = second.get("_held", 0)
            if held <= 0 and second["cooldown"] > 1e-8:
                return
            if held > 0 and not trigger:
                second["_pending"] = True
            if trigger or held > 0:
                held += DT
                second["_held"], second["charge"] = held, min(stats["charge"], held)
                if (second.get("_pending") and held+1e-8 >= stats["min_charge"]) or held+1e-8 >= stats["charge"]+stats["hold_s"]:
                    self.release_laser(entity, second, held)
        elif second["kind"] == "lightning" and trigger and second["cooldown"] <= 1e-8 and entity["energy"] >= stats["energy"]:
            second["cooldown"] = stats["cooldown"]
            entity["energy"] -= stats["energy"]
            entity["_spent"] = self.t
            if entity["id"] == 0:
                self.secondary_shots += 1
                if self.first_secondary is None:
                    self.first_secondary = self.t
            targets = []
            for target in self.entities:
                if target is entity or target["hp"] <= 0:
                    continue
                d = math.dist(entity["pos"][:2], target["pos"][:2])
                yaw = math.atan2(target["pos"][1]-entity["pos"][1], target["pos"][0]-entity["pos"][0])
                origin = [*entity["pos"][:2], entity["pos"][2]+entity["stats"]["muzzle_height"]]
                center = [*target["pos"][:2], target["pos"][2]+target["stats"]["height"]*.5]
                if d <= stats["range"] and abs(wrapped(yaw-entity["aim"][0])) <= math.radians(stats["cone_deg"])/2 and self.world.line_clear(origin, center):
                    targets.append((d, target))
            if targets:
                self.secondary_hit(entity, min(targets, key=lambda item: item[0])[1], "lightning", stats["damage"])

    def collect(self, action):
        pickup = next((p for p in self.pickups if p["id"] == action.get("take")), None)
        if pickup is None:
            return
        d = math.dist(self.me["pos"][:2], pickup["pos"][:2])
        if d <= self.config["loot"]["pickup_radius"] and abs(self.me["pos"][2]-pickup["pos"][2]) <= 4 and self.me["weapons"][1] is None:
            stats = copy.deepcopy(self.config["weapons"][pickup["kind"]])
            equip = max(self.config["loot"]["equip_s"], stats["cooldown"])
            self.me["weapons"][1] = dict(kind=pickup["kind"], stats=stats, cooldown=equip, charge=0)
            self.events.append(dict(type="took", id=pickup["id"], kind=pickup["kind"], slot=1))
            self.pickups.remove(pickup)
            self.acquired_at, self.equip_ready_at = self.t, self.t+equip

    def run(self):
        action = {}
        for tick in range(round(self.seconds/DT)):
            self.t = 30+tick*DT
            if tick % 2 == 0:
                obs = self.observation(tick)
                action = self.bot.act(obs)
                self.metrics["ignored_jump_requests"] += bool(action.get("jump"))
                self.trace.append(dict(t=round(self.t-30, 3), pos=list(self.me["pos"]), hp=self.me["hp"],
                    enemy_hp=self.enemy["hp"], reload=self.me["weapons"][0]["reload"],
                    arm=getattr(getattr(self.bot, "reload_arm", None), "state", "absent"),
                    mode=self.bot.mode, aim=action["aim"], fire=action["fire"]))
            actions = {0: action, 1: self.enemy_action(self.enemy, tick)}
            for entity in self.entities:
                if entity["hp"] > 0:
                    self.move_entity(entity, actions[entity["id"]])
                    self.weapon(entity, actions[entity["id"]])
            self.projectiles()
            self.collect(action)
            if self.enemy["hp"] <= 0:
                self.kill_at = self.t
                break
            if self.me["hp"] <= 0:
                break
        return dict(kind=self.kind, pickup_at=None if self.acquired_at is None else self.acquired_at-30,
            equip_ready=None if self.equip_ready_at is None else self.equip_ready_at-30,
            first_secondary=None if self.first_secondary is None else self.first_secondary-30,
            secondary_shots=self.secondary_shots, secondary_hits=self.secondary_hits,
            secondary_damage=self.secondary_damage, hp=self.me["hp"], enemy_hp=self.enemy["hp"],
            energy=self.me["energy"], healing=self.metrics["healing"], gun_shots=self.metrics["shots"],
            damage_dealt=self.metrics["damage_dealt"], damage_taken=self.metrics["damage_taken"],
            kill_at=None if self.kill_at is None else self.kill_at-30,
            ignored_jumps=self.metrics["ignored_jump_requests"])


class ReloadArmFeedbackTests(unittest.TestCase):
    def test_real_laser_pickup_respects_equip_and_fires_actual_beam(self):
        result = ArmFeedback().run()
        self.assertIsNotNone(result["pickup_at"])
        self.assertLessEqual(result["pickup_at"], 3)
        self.assertGreaterEqual(result["first_secondary"], result["equip_ready"])
        self.assertGreaterEqual(result["first_secondary"]+.051, result["equip_ready"]+.75)
        self.assertGreater(result["secondary_hits"], 0)
        self.assertGreater(result["secondary_damage"], 0)

    def test_real_lightning_pickup_only_damages_inside_its_cone_and_range(self):
        result = ArmFeedback(kind="lightning").run()
        self.assertIsNotNone(result["pickup_at"])
        if result["first_secondary"] is not None:
            self.assertGreaterEqual(result["first_secondary"], result["equip_ready"])
        self.assertLessEqual(result["secondary_hits"], result["secondary_shots"])

    def test_lightning_does_not_invent_damage_outside_range_or_actual_cone(self):
        model = ArmFeedback(kind="lightning")
        stats = copy.deepcopy(model.config["weapons"]["lightning"])
        model.me["weapons"][1] = dict(kind="lightning", stats=stats, cooldown=0, charge=0)
        model.enemy["pos"] = [60, 0, 0]
        model.me["aim"] = [0, 0]
        model.weapon(model.me, {"fire": [False, True]})
        self.assertEqual(model.secondary_hits, 0)
        model.enemy["pos"] = [40, 0, 0]
        model.me["aim"] = [math.pi/2, 0]
        model.me["weapons"][1]["cooldown"] = 0
        model.weapon(model.me, {"fire": [False, True]})
        self.assertEqual(model.secondary_hits, 0)
        model.me["aim"] = [0, 0]
        model.me["weapons"][1]["cooldown"] = 0
        model.weapon(model.me, {"fire": [False, True]})
        self.assertEqual(model.secondary_hits, 1)
        self.assertEqual(model.secondary_damage, 60)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--simulate":
        kind = sys.argv[3] if len(sys.argv) > 3 else "laser"
        result = ArmFeedback(PROJECT, kind=kind).run()
        print(json.dumps(result))
    else:
        unittest.main()
