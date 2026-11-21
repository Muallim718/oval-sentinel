"""Build and use a gun/laser kit without abandoning an urgent fight or escape.

Only observed floor weapons are pursued. The inherited routing and pressure
checks are our original opening policy, extended to permit a deliberate swap
and a complete, checked route before leaving for an obscured pickup.
"""
import copy
import math
import time

from . import tuning
from .geometry import distance
from .opener import Mission, Opener


class LaserDoctrine(Opener):
    MAX_DISTANCE = 160.0
    ROUTE_LIMIT = 210.0
    ROUTE_SECONDS = .004

    def __init__(self, world, config):
        super().__init__(world, config)
        self.route = []
        self.checked_at = -100.0
        self.checked_threats = None
        self.route_body = None

    def cancel(self, reason="ordinary policy regained control", now=None, reject=False):
        super().cancel(reason, now, reject)
        self.route = []
        self.checked_threats = None
        self.route_body = None

    @property
    def pending(self):
        return self.current is not None

    @staticmethod
    def _swap_slot(me):
        empty = next((i for i, weapon in enumerate(me["weapons"]) if weapon is None), None)
        if empty is not None:
            return empty, False
        other = next((i for i, weapon in enumerate(me["weapons"])
                      if weapon and weapon["kind"] != "gun" and not weapon.get("charge", 0)), None)
        return other, other is not None

    def _eligible(self, obs, recovering):
        me = obs["self"]
        return (not recovering and me["hp"] >= me["max_hp"]*.80 and me["in_zone"] and
                me["grounded"] and obs["t"]-self.last_hit >= 2.5 and
                not any(w and w["kind"] == "laser" for w in me["weapons"]) and
                self._swap_slot(me)[0] is not None and
                me["pos"][2]-self.world.ground(*me["pos"][:2]) <= me["stats"]["step_up"]+.5)

    def _safe_point(self, obs, point, threats, remaining):
        # Evaluate the same actual firing-lane pressure at the corridor point,
        # rather than declaring an exposed endpoint safe from our current wall.
        hypothetical = dict(obs)
        hypothetical["self"] = {**obs["self"], "pos": point}
        if self._pressure(hypothetical, threats, remaining):
            return False
        for enemy in obs["mechs"]:
            if enemy.get("kind") != "npc" or distance(point, enemy["pos"]) > 48:
                continue
            eye = [point[0], point[1], point[2]+obs["self"]["stats"]["eye_height"]]
            target = list(enemy["pos"])
            target[2] += self.config["npc"].get("height", 3.5)*.5
            if self.world.line_clear(eye, target):
                return False
        return True

    def _certify(self, obs, route, threats, circle):
        deadline = time.perf_counter()+self.ROUTE_SECONDS
        me, stats = obs["self"], obs["self"]["stats"]
        points = [tuple(me["pos"])]+list(route)
        total = sum(distance(a, b) for a, b in zip(points, points[1:]))
        if total > self.ROUTE_LIMIT:
            return False
        # Maximal 25m spacing includes every bend, keeping the certificate
        # bounded even on an unexpectedly fragmented route.
        samples = [points[0]]
        for start, end in zip(points, points[1:]):
            count = max(1, math.ceil(distance(start, end)/25))
            for i in range(1, count+1):
                x, y = (start[j]+(end[j]-start[j])*i/count for j in range(2))
                samples.append((x, y, self.world.ground(x, y)))
        if len(samples) > 24:
            return False
        remaining = max(self.config["weapons"]["laser"]["cooldown"], total/self._speed(me))
        for a, b in zip(points, points[1:]):
            if time.perf_counter() >= deadline or not self.world.walk_clear(
                    a, b, stats["radius"]+.3, stats["height"], stats["step_up"], stats["max_slope_deg"]):
                return False
        for point in samples:
            if (time.perf_counter() >= deadline or
                    distance(point, circle[0]) >= circle[1]-stats["radius"]-3 or
                    not self._safe_point(obs, point, threats, remaining)):
                return False
        return True

    def _complete_route(self, obs, goal, circle):
        me, stats = obs["self"], obs["self"]["stats"]
        if self.world.walk_clear(me["pos"], goal, stats["radius"]+.3, stats["height"],
                                 stats["step_up"], stats["max_slope_deg"]):
            return [tuple(goal)]
        path = self.nav.plan(me["pos"], goal, circle)
        if not self.nav.search_done:
            return None
        end = path[-1] if path else me["pos"]
        if distance(end, goal) > 9 or not self.world.walk_clear(
                end, goal, stats["radius"]+.3, stats["height"], stats["step_up"], stats["max_slope_deg"]):
            return False
        points = path+[tuple(goal)]
        # Remove short grid segments before repeated corridor certification.
        # Each selected leg is checked with the current live body.
        compact, previous, index = [], me["pos"], 0
        while index < len(points):
            chosen = index
            for j in range(min(len(points)-1, index+8), index-1, -1):
                if self.world.walk_clear(previous, points[j], stats["radius"]+.3,
                        stats["height"], stats["step_up"], stats["max_slope_deg"]):
                    chosen = j
                    break
            compact.append(tuple(points[chosen]))
            previous, index = points[chosen], chosen+1
        return compact

    def choose(self, obs, threats, circle, *, recovering=False):
        self.update(obs)
        now, me = obs["t"], obs["self"]
        if (not self._eligible(obs, recovering) or obs["alive"] <= 2 or
                distance(me["pos"], circle[0]) >= circle[1]-me["stats"]["radius"]-5):
            self.cancel("laser acquisition yields to equipment, health, terrain, or final duel")
            return None
        if not self._safe_point(obs, me["pos"], threats, 3):
            self.cancel("hunter pressure takes priority over laser planning", now, True)
            return None
        self.nav.set_body(me["stats"])
        if self.current is None:
            candidates = []
            for item in self.loot.get("pickups"):
                if item["kind"] != "laser" or self.rejected.get(("weapon", item["id"]), -1) > now:
                    continue
                goal = self._point(item["pos"], me, circle)
                if goal and distance(me["pos"], goal) <= self.MAX_DISTANCE:
                    candidates.append((distance(me["pos"], goal), item["id"], item, goal))
            if not candidates:
                return None
            travel, item_id, item, goal = min(candidates)
            self.current = {"kind": "weapon", "id": item_id, "target": dict(item),
                "phase": "approach", "goal": goal, "deadline": now+min(24, 4+travel/me["stats"]["walk_speed"]*1.5),
                "progress_pos": tuple(me["pos"]), "progress_at": now}
        current = self.current
        item = next((p for p in self.loot.get("pickups") if p["id"] == current["id"]), None)
        goal = self._point(item["pos"], me, circle) if item else None
        if goal is None or now >= current["deadline"]:
            self.cancel("laser objective expired or lost its body/zone clearance", now, True)
            return None
        if distance(me["pos"], current["progress_pos"]) >= 2:
            current["progress_pos"], current["progress_at"] = tuple(me["pos"]), now
        elif now-current["progress_at"] >= 3:
            self.cancel("laser mission made no physical progress", now, True)
            return None
        body = (me["stats"]["radius"], me["stats"]["height"])
        if not self.route or body != self.route_body:
            route = self._complete_route(obs, goal, circle)
            if route is None:
                self.state, self.reason = "planning", "finish checked laser corridor before committing"
                return None
            if route is False:
                self.cancel("laser has no reachable ground route", now, True)
                return None
            self.route = list(route)
            self.route_body = body
            self.checked_threats = None
        while len(self.route) > 1 and distance(me["pos"], self.route[0]) < 5:
            self.route.pop(0)
        signature = tuple((e["id"], round(e["pos"][0]/5), round(e["pos"][1]/5))
                          for e, confidence in threats[:8])
        if now-self.checked_at >= .5 or signature != self.checked_threats:
            if not self._certify(obs, self.route, threats, circle):
                self.cancel("laser corridor became exposed, blocked, or over budget", now, True)
                return None
            self.checked_at, self.checked_threats = now, signature
        if not self._safe_point(obs, me["pos"], threats, 1.65):
            self.cancel("laser acquisition interrupted by real pressure", now, True)
            return None
        waypoint = self.route[0]
        for point in reversed(self.route[:5]):
            if self.world.walk_clear(me["pos"], point, me["stats"]["radius"]+.3,
                    me["stats"]["height"], me["stats"]["step_up"], me["stats"]["max_slope_deg"]):
                waypoint = point
                break
        self.state, self.reason = "approach", "secure observed laser and keep the arm gun"
        self.plan = Mission(tuple(goal), "laser", current["id"], None,
            me["energy"] > self.ENERGY_RESERVE+15 and distance(me["pos"], goal) > 10,
            self.reason, tuple(waypoint))
        return self.plan

    def pickup_action(self, obs, threats, circle, *, recovering=False):
        self.update(obs)
        if not self._eligible(obs, recovering):
            return {}
        me = obs["self"]
        near = [p for p in obs["pickups"] if p["kind"] == "laser" and
                distance(me["pos"], p["pos"]) <= self.config["loot"]["pickup_radius"] and
                abs(me["pos"][2]-p["pos"][2]) <= 4 and self._point(p["pos"], me, circle)]
        if not near or not self._safe_point(obs, me["pos"], threats,
                self.config["weapons"]["laser"]["cooldown"]):
            return {}
        item = min(near, key=lambda p: (distance(me["pos"], p["pos"]), p["id"]))
        slot, replacing = self._swap_slot(me)
        result = {"take": item["id"]}
        if replacing:
            result["drop"] = slot
        return result

    @staticmethod
    def preferred_range(me, enemy, circle):
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        laser = next((w for w in me["weapons"] if w and w["kind"] == "laser"), None)
        if not gun or not laser:
            return None
        overlap = min(gun["stats"]["range"], laser["stats"]["range"])
        desired = min(150, overlap*.65)
        if "mortar" in enemy.get("weapons", []):
            desired = min(165, overlap*.72)
        # A target near the circle's center cannot be fought from beyond its
        # radius; do not request an unreachable ring through the storm.
        available = max(6, distance(enemy.get("pos", circle[0]), circle[0])+
                        circle[1]-me["stats"]["radius"]-6)
        return min(desired, circle[1]*1.45, available)

    @staticmethod
    def _dps(kind, stats):
        if kind == "laser":
            return stats["damage"]/(stats["charge"]+stats["cooldown"])
        if kind == "gun":
            return stats["damage"]*stats["mag"]/(stats["mag"]*stats["cooldown"]+stats["reload"])
        return 0

    def pick_upgrade(self, obs):
        if not obs.get("offer") or not any(w and w["kind"] == "laser" for w in obs["self"]["weapons"]):
            return None
        upgrades = {u["id"]: u for u in self.config["upgrades"]}
        held = {w["kind"]: w for w in obs["self"]["weapons"] if w}
        values = []
        for choice in obs["offer"]["choices"]:
            value = tuning.UPGRADE_VALUE.get(choice["id"], 0)
            upgrade = upgrades.get(choice["id"], {})
            kind = upgrade.get("requires")
            if kind in ("gun", "laser") and kind in held:
                before = held[kind]["stats"]
                after = copy.copy(before)
                for effect in upgrade.get("effects", []):
                    prefix = "weapons."+kind+"."
                    if effect["path"].startswith(prefix):
                        key = effect["path"][len(prefix):]
                        after[key] = after[key]*effect.get("mul", 1)+effect.get("add", 0)
                gain = self._dps(kind, after)-self._dps(kind, before)
                if gain > 0:
                    value = 88+gain
            values.append(value)
        return max(range(len(values)), key=lambda i: values[i])
