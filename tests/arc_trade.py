"""Weapon and collision primitives for the public-map arc-retreat feedback.

Every hit uses the actual torso/barrel and a physical cylinder intersection.
Gun spread, magazine/reload, laser charge/cooldown, arc range and shorts use
public config. The pursuing policy is declared test AI, not private house AI.
"""
import copy
import json
import math
from pathlib import Path
import random
import sys
import unittest

from test_bot import ROOT as SOURCE
sys.path.insert(0, str(SOURCE/"tools"))
from test_bot import fixture
from arc_physics import move
from ground_lab import cylinder_entry, lead, slew, wrapped
from sentinel.geometry import World, distance


class ArcPhysicsBase:
    def __init__(self, enabled, gap=55, seed=47, before_turn=False, seconds=8.5):
        hello, obs = fixture()
        self.config = hello["config"]
        self.world = World(SOURCE/"arena")
        self.enabled, self.before_turn, self.seconds = enabled, before_turn, seconds
        self.me = copy.deepcopy(obs["self"])
        self.me.update(id=0, pos=[30, 10, self.world.ground(30, 10)], vel=[-11.7, 0, 0],
            hp=1400, max_hp=1400, energy=100, cubes=0, grounded=True, in_zone=True)
        self.me["weapons"][0].update(ammo=12, reload=0, cooldown=0)
        self.me["weapons"][1] = self.weapon("laser")
        self.enemy = copy.deepcopy(self.me)
        self.enemy.update(id=1, kind="mech", pos=[30+gap, 10, self.world.ground(30+gap, 10)],
                          vel=[-11.7, 0, 0])
        self.enemy["weapons"][1] = self.weapon("lightning")
        self.entities = [self.me, self.enemy]
        for entity in self.entities:
            target = self.entities[1-entity["id"]]
            origin = [*entity["pos"][:2], entity["pos"][2]+7]
            point = [*target["pos"][:2], target["pos"][2]+4.5]
            entity["aim"] = lead(origin, point, target["vel"], 252)
            assert self.world.body_clear(*entity["pos"], 2.5, 9)
        assert self.world.walk_clear(self.me["pos"], self.enemy["pos"], 2.8, 9, 1.2, 50)
        self.rng = [random.Random(seed), random.Random(seed+1009)]
        self.bullets, self.events, self.trace = [], [], []
        self.damage = [{kind: 0 for kind in ("gun", "laser", "lightning")} for _ in range(2)]
        self.hits = [{kind: 0 for kind in ("gun", "laser", "lightning")} for _ in range(2)]
        self.shots = [{kind: 0 for kind in ("gun", "laser", "lightning")} for _ in range(2)]
        self.short_count = self.boost_seconds = self.arc_seconds = 0
        self.min_energy, self.collisions, self.now = 100, 0, 0

    def weapon(self, kind):
        return dict(kind=kind, charge=0, cooldown=0, stats=copy.deepcopy(self.config["weapons"][kind]))

    @staticmethod
    def view(entity):
        return {key: copy.deepcopy(entity[key]) for key in
                ("id", "kind", "pos", "vel", "hp", "max_hp", "aim", "cubes")}

    def ray(self, actor, maximum, aim=None):
        yaw, pitch = aim or actor["aim"]
        direction = [math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)]
        muzzle = [*actor["pos"][:2], actor["pos"][2]+actor["stats"]["muzzle_height"]]
        origin = [muzzle[i]+direction[i]*(actor["stats"]["radius"]+.5) for i in range(3)]
        return muzzle, origin, [origin[i]+direction[i]*maximum for i in range(3)], direction

    def deal(self, by, target, kind, amount):
        target["hp"] -= amount
        self.damage[by][kind] += amount
        self.hits[by][kind] += 1
        if target is self.me:
            self.events.append(dict(type="damaged", weapon=kind, amount=amount, by=by, bearing=0))

    def shot(self, actor, action):
        target = self.entities[1-actor["id"]]
        gun = actor["weapons"][0]
        gun["cooldown"] -= .05
        if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < gun["stats"]["mag"]:
            gun["reload"] = gun["stats"]["reload"]
        if gun["reload"] > 0:
            gun["reload"] = max(0, gun["reload"]-.05)
            if gun["reload"] <= 1e-9:
                gun["reload"], gun["ammo"] = 0, gun["stats"]["mag"]
        if action["fire"][0] and gun["ammo"] > 0 and gun["reload"] == 0 and gun["cooldown"] <= 1e-9:
            gun["ammo"] -= 1
            gun["cooldown"] += gun["stats"]["cooldown"]
            spread = math.radians(gun["stats"]["spread_deg"])
            aim = [actor["aim"][i]+self.rng[actor["id"]].gauss(0, spread) for i in range(2)]
            muzzle, origin, _, direction = self.ray(actor, gun["stats"]["range"], aim)
            if self.world.line_clear(muzzle, origin):
                self.bullets.append(dict(by=actor["id"], pos=origin,
                    vel=[v*gun["stats"]["speed"] for v in direction], remaining=gun["stats"]["range"]))
            self.shots[actor["id"]]["gun"] += 1
        second = actor["weapons"][1]
        second["cooldown"] = max(0, second["cooldown"]-.05)
        if second["kind"] == "laser":
            stats, held = second["stats"], second.get("_held", 0)
            trigger = action["fire"][1]
            if held > 0 and not trigger:
                second["_pending"] = True
            if held > 0 or (trigger and second["cooldown"] <= 0):
                held += .05
                second["_held"], second["charge"] = held, min(stats["charge"], held)
                if ((second.get("_pending") and held+1e-9 >= stats["min_charge"]) or
                        held+1e-9 >= stats["charge"]+stats["hold_s"]):
                    muzzle, origin, end, _ = self.ray(actor, stats["range"])
                    entry = cylinder_entry(origin, end, target["pos"], target["stats"]["radius"], target["stats"]["height"])
                    if entry is not None:
                        point = [origin[i]+(end[i]-origin[i])*entry for i in range(3)]
                        if self.world.line_clear(muzzle, origin) and self.world.line_clear(origin, point):
                            amount = stats["damage"]*(stats["min_frac"]+(1-stats["min_frac"])*min(1, held/stats["charge"]))
                            self.deal(actor["id"], target, "laser", amount)
                    self.shots[actor["id"]]["laser"] += 1
                    second.update(charge=0, _held=0, _pending=False, cooldown=stats["cooldown"])
        elif action["fire"][1] and second["cooldown"] <= 1e-9 and actor["energy"] >= second["stats"]["energy"]:
            stats = second["stats"]
            actor["energy"] -= stats["energy"]
            actor["_quiet"] = 0
            second["cooldown"] += stats["cooldown"]
            self.shots[actor["id"]]["lightning"] += 1
            bearing = math.atan2(target["pos"][1]-actor["pos"][1], target["pos"][0]-actor["pos"][0])
            origin = [*actor["pos"][:2], actor["pos"][2]+7]
            point = [*target["pos"][:2], target["pos"][2]+4.5]
            if (distance(actor["pos"], target["pos"]) <= stats["range"] and
                    abs(wrapped(bearing-actor["aim"][0])) <= math.radians(stats["cone_deg"])/2 and
                    self.world.line_clear(origin, point)):
                self.deal(actor["id"], target, "lightning", stats["damage"])
                laser = target["weapons"][1]
                if laser["kind"] == "laser":
                    self.short_count += bool(laser["charge"] > 0)
                    laser.update(charge=0, _held=0, _pending=False, cooldown=max(laser["cooldown"], stats["short_s"]))
                    self.events.append(dict(type="effect", effect="short", by=actor["id"]))

    def projectiles(self, before_positions):
        live = []
        for bullet in self.bullets:
            target = self.entities[1-bullet["by"]]
            a = bullet["pos"]
            b = [a[i]+bullet["vel"][i]*.05 for i in range(3)]
            relative_a = [a[i]-before_positions[target["id"]][i] for i in range(3)]
            relative_b = [b[i]-target["pos"][i] for i in range(3)]
            entry = cylinder_entry(relative_a, relative_b, [0, 0, 0], target["stats"]["radius"], target["stats"]["height"])
            hit = False
            if entry is not None:
                point = [a[i]+(b[i]-a[i])*entry for i in range(3)]
                hit = self.world.line_clear(a, point)
            if hit:
                # Both actors keep facing the opponent in this straight lane.
                self.deal(bullet["by"], target, "gun", 45)
            else:
                bullet["remaining"] -= math.dist(a, b)
                if bullet["remaining"] > 0 and self.world.line_clear(a, b):
                    bullet["pos"] = b
                    live.append(bullet)
        self.bullets = live
