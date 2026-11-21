"""Early power acquisition with explicit attack, confirmation, and collection.

This is an optional opening policy. Damage, recovery, zone urgency, or a hunter
that can interrupt the mission hands control back to the ordinary bot.
"""
from dataclasses import dataclass
import math

from .combat import Combat
from .cover import firing_lane
from .geometry import distance, unit
from .memory import LootMemory
from .navigation import Navigator


@dataclass(frozen=True)
class Mission:
    goal: tuple
    kind: str
    target_id: int | None
    exclusive_target: dict | None
    sprint: bool
    reason: str
    waypoint: tuple | None = None


class Opener:
    START_UNTIL = 55.0
    FINISH_UNTIL = 60.0
    MAX_DISTANCE = 160.0
    ENERGY_RESERVE = 38.0

    def __init__(self, world, config, navigator=None):
        self.world, self.config = world, config
        self.nav = navigator or Navigator(world, config["mech"])
        self.combat = Combat(world, config)
        self.loot = LootMemory()
        self.current = None
        self.plan = None
        self.state = "idle"
        self.reason = "opening has no selected power source"
        self.last_hit = -100
        self.last_tick = None
        self.rejected = {}
        self.completed = 0

    def cancel(self, reason="ordinary policy regained control", now=None, reject=False):
        if reject and self.current and now is not None:
            self.rejected[(self.current["kind"], self.current["id"])] = now+6
        self.current, self.plan = None, None
        self.state, self.reason = "idle", reason
        self.nav.search = None
        self.nav.path = []

    def _complete(self):
        self.completed += 1
        self.cancel("power source collected")

    def update(self, obs):
        marker = (obs["tick"], obs["t"])
        if marker == self.last_tick:
            return
        self.last_tick = marker
        self.loot.update(obs, self.world)
        now, me = obs["t"], obs["self"]
        self.rejected = {key: until for key, until in self.rejected.items() if until > now}
        for event in obs["events"]:
            if event["type"] == "damaged" and event.get("amount", 0) > 0:
                expected_npc = (self.current and self.current["kind"] == "npc" and
                                event.get("weapon") == "npc" and event.get("by") == self.current["id"])
                if expected_npc:
                    self.current["npc_damage"] += event["amount"]
                    if self.current["npc_damage"] > 75:
                        self.last_hit = now
                else:
                    self.last_hit = now
        current = self.current
        if current is None:
            return
        if current["kind"] == "weapon":
            if (any(event["type"] == "took" and event["id"] == current["id"] for event in obs["events"]) or
                    any(w and w["kind"] == current["target"]["kind"] for w in me["weapons"])):
                self._complete()
            return
        if me["cubes"] >= current["before_cubes"]+current["expected_cubes"]:
            self._complete()
            return
        if current["phase"] != "attack":
            return
        category = obs["crates"] if current["kind"] == "crate" else obs["mechs"]
        visible = next((item for item in category if item["id"] == current["id"]), None)
        old_hp = current["target"]["hp"]
        if visible:
            current["target"] = dict(visible)
            current["last_seen"] = now
        else:
            current["target"]["hp"] -= sum(event["amount"] for event in obs["events"]
                if event["type"] == "hit" and event["target"] == current["id"])
        confirmed_dead = current["target"]["hp"] <= 0 or any(
            event["type"] == "kill" and event["target"] == current["id"] for event in obs["events"])
        if confirmed_dead:
            current["phase"] = "collect"
            current["deadline"] = min(self.FINISH_UNTIL, now+6)
            current["progress_at"] = now
            current["kill_position"] = tuple(current["target"]["pos"])
        elif not visible and now-current["last_seen"] > .4:
            self.cancel("farm target disappeared without confirmed death", now, True)
        elif current["target"]["hp"] < old_hp:
            current["progress_at"] = now

    def _point(self, pos, me, circle):
        ground = self.world.ground(*pos[:2])
        if abs(pos[2]-ground) >= 4:
            return None
        point = (pos[0], pos[1], ground)
        if distance(point, circle[0]) >= circle[1]-me["stats"]["radius"]-5:
            return None
        stats = me["stats"]
        return point if self.world.body_clear(*point, stats["radius"]+.3,
                        stats["height"], stats["step_up"]) else None

    def _speed(self, me):
        return me["stats"]["boost_speed"] if me["energy"] > self.ENERGY_RESERVE+15 else me["stats"]["walk_speed"]

    def _attack_goal(self, target, kind, me):
        away = unit(me["pos"][0]-target["pos"][0], me["pos"][1]-target["pos"][1])
        if away == (0, 0):
            away = (1, 0)
        stand = 9 if kind == "crate" else 20
        point = (target["pos"][0]+away[0]*stand, target["pos"][1]+away[1]*stand)
        return (*point, self.world.ground(*point))

    def _candidates(self, obs, circle):
        me = obs["self"]
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        held = {w["kind"] for w in me["weapons"] if w}
        candidates = []
        if me["cubes"] < 6:
            for target in self.loot.get("cubes"):
                point = self._point(target["pos"], me, circle)
                travel = distance(me["pos"], target["pos"])
                if point and travel <= 80:
                    eta = travel/self._speed(me)+.1
                    candidates.append((48/(eta+3), "cube", target, point, eta))
        for target in self.loot.get("pickups"):
            if target["kind"] in held or target["kind"] == "gun" or me["weapons"][1] is not None:
                continue
            point = self._point(target["pos"], me, circle)
            travel = distance(me["pos"], target["pos"])
            if point and travel <= self.MAX_DISTANCE:
                value = 95 if target["kind"] in ("laser", "lightning") else 48
                eta = travel/self._speed(me)+self.config["loot"].get("equip_s", 1)
                candidates.append((value/(eta+3), "weapon", target, point, eta))
        if gun and gun.get("reload", 0) <= 0 and me["cubes"] < 6:
            damage = gun["stats"]["damage"]*(1+self.config["cubes"]["damage_per_cube"]*
                                             min(me["cubes"], self.config["cubes"]["stat_cap"]))
            sources = [("crate", target) for target in self.loot.get("crates")]
            sources += [("npc", target) for target in obs["mechs"] if target.get("kind") == "npc"]
            for kind, target in sources:
                point = self._point(target["pos"], me, circle)
                travel = distance(me["pos"], target["pos"])
                reliability = .95 if kind == "crate" else .85
                rounds = math.ceil(target.get("hp", 350)/(damage*reliability))
                if not point or travel > 115 or rounds > gun.get("ammo", 0):
                    continue
                goal = self._attack_goal(target, kind, me)
                if self._point(goal, me, circle) is None:
                    continue
                kill_time = max(.05, gun.get("cooldown", 0))+(rounds-1)*gun["stats"]["cooldown"]+travel/gun["stats"]["speed"]
                eta = max(kill_time, max(0, travel-3)/self._speed(me))+.2
                value = 65 if kind == "crate" else 90
                candidates.append((value/(eta+3), kind, target, goal, eta))
        return sorted((candidate for candidate in candidates
                       if self.rejected.get((candidate[1], candidate[2]["id"]), -1) <= obs["t"]),
                      key=lambda item: (-item[0], item[2]["id"]))

    def _route(self, me, goal, circle):
        stats = me["stats"]
        if self.world.walk_clear(me["pos"], goal, stats["radius"]+.3, stats["height"],
                                 stats["step_up"], stats["max_slope_deg"]):
            return tuple(goal)
        path = self.nav.plan(me["pos"], goal, circle)
        if self.nav.search_done:
            end = path[-1] if path else me["pos"]
            if distance(end, goal) > 9 or not self.world.walk_clear(end, goal,
                    stats["radius"]+.3, stats["height"], stats["step_up"], stats["max_slope_deg"]):
                return False
            path = path+[tuple(goal)]
        for point in reversed(path[:5]):
            if self.world.walk_clear(me["pos"], point, stats["radius"]+.3, stats["height"],
                                     stats["step_up"], stats["max_slope_deg"]):
                return tuple(point)
        return None

    def _pressure(self, obs, threats, remaining):
        me = obs["self"]
        enemies = {enemy["id"]: enemy for enemy, confidence in threats
                   if enemy.get("kind") == "mech" and confidence >= .25}
        enemies.update({enemy["id"]: enemy for enemy in obs["mechs"] if enemy.get("kind") == "mech"})
        risk = 0.0
        for enemy in enemies.values():
            dist = distance(me["pos"], enemy["pos"])
            if dist < 65:
                return True
            if dist > 350 or not firing_lane(self.world, self.config, me["pos"], me, enemy)[0]:
                continue
            kinds = enemy.get("weapons", ["gun"])
            if enemy.get("charging") and "laser" in kinds and dist <= self.config["weapons"]["laser"]["range"]:
                return True
            if dist < 120:
                return True
            window = min(3, remaining)
            if "gun" in kinds and dist <= self.config["weapons"]["gun"]["range"]:
                gun = self.config["weapons"]["gun"]
                risk += max(0, window-dist/gun["speed"])*gun["damage"]/gun["cooldown"]
            if "laser" in kinds and dist <= self.config["weapons"]["laser"]["range"] and window >= .75:
                risk += self.config["weapons"]["laser"]["damage"]
            if "mortar" in kinds and window >= dist/self.config["weapons"]["mortar"]["speed"]:
                risk += self.config["weapons"]["mortar"]["damage"]
        for projectile in obs["projectiles"]:
            p, velocity = projectile["pos"], projectile["vel"]
            dx, dy = p[0]-me["pos"][0], p[1]-me["pos"][1]
            vx, vy = velocity[0]-me["vel"][0], velocity[1]-me["vel"][1]
            when = max(0, min(.7, -(dx*vx+dy*vy)/(vx*vx+vy*vy or 1)))
            radius = me["stats"]["radius"]+(8 if projectile["kind"] == "mortar" else 1)
            if math.hypot(dx+vx*when, dy+vy*when) < radius:
                z = p[2]+velocity[2]*when
                if projectile["kind"] == "mortar":
                    z -= self.config["weapons"]["mortar"]["gravity"]*when*when/2
                if me["pos"][2]-3 < z < me["pos"][2]+me["stats"]["height"]+3:
                    risk += (200 if projectile["kind"] == "mortar" else
                             self.config["npc"]["damage"] if projectile["kind"] == "npc" else 45)
        return risk > me["max_hp"]*.10

    def choose(self, obs, threats, circle, *, recovering=False):
        if obs["t"] >= self.FINISH_UNTIL:
            if self.current is not None:
                self.cancel("opening period completed")
            return None
        self.update(obs)
        now, me = obs["t"], obs["self"]
        if (recovering or me["hp"] < me["max_hp"]*.90 or not me["in_zone"] or not me["grounded"] or
                now-self.last_hit < 2.5 or now >= self.FINISH_UNTIL or
                me["pos"][2]-self.world.ground(*me["pos"][:2]) > me["stats"]["step_up"]+.5):
            self.cancel("opening yields to health, pressure, zone, or elevation")
            return None
        self.nav.set_body(me["stats"])
        if self.current is None:
            if now >= self.START_UNTIL:
                return None
            candidates = self._candidates(obs, circle)
            if not candidates:
                self.plan = None
                return None
            _, kind, target, goal, eta = candidates[0]
            self.current = {"kind": kind, "id": target["id"], "target": dict(target),
                "phase": "approach" if kind == "weapon" else "collect" if kind == "cube" else "attack", "goal": goal,
                "deadline": min(self.FINISH_UNTIL, now+max(5, eta*1.7+2)),
                "before_cubes": me["cubes"], "expected_cubes": 2 if kind == "npc" else 1,
                "last_seen": now, "progress_at": now, "progress_pos": tuple(me["pos"]),
                "npc_damage": 0, "kill_position": tuple(target["pos"])}
        current = self.current
        if current["phase"] == "attack" and not any(
                weapon and weapon["kind"] == "gun" for weapon in me["weapons"]):
            self.cancel("farm gun is no longer available", now, True)
            return None
        if now > current["deadline"]:
            self.cancel("opening mission timed out", now, True)
            return None
        if current["kind"] == "weapon":
            target = next((item for item in self.loot.get("pickups") if item["id"] == current["id"]), None)
            if target is None:
                self.cancel("selected floor weapon is gone", now, True)
                return None
            goal = self._point(target["pos"], me, circle)
            exclusive = None
            target_id = current["id"]
        elif current["phase"] == "collect":
            cubes = [item for item in self.loot.get("cubes")
                     if distance(item["pos"], current["kill_position"]) < 18]
            cubes.sort(key=lambda item: (distance(me["pos"], item["pos"]), item["id"]))
            goal = self._point(cubes[0]["pos"] if cubes else current["kill_position"], me, circle)
            exclusive = None
            target_id = cubes[0]["id"] if cubes else None
        else:
            target = current["target"]
            goal = self._point(self._attack_goal(target, current["kind"], me), me, circle)
            solution = self.combat.solve(me, target, next(w for w in me["weapons"] if w and w["kind"] == "gun"))
            exclusive = dict(target) if solution and me["stats"]["min_pitch"] <= solution[0][1] <= me["stats"]["max_pitch"] else None
            target_id = current["id"]
        if goal is None:
            self.cancel("mission destination is outside live body or zone clearance", now, True)
            return None
        remaining = max(.3, distance(me["pos"], goal)/self._speed(me))
        if current["phase"] == "attack":
            gun = next(w for w in me["weapons"] if w and w["kind"] == "gun")
            remaining = max(remaining, current["target"]["hp"]/max(1, gun["stats"]["damage"])*gun["stats"]["cooldown"]+.3)
        if self._pressure(obs, threats, remaining):
            self.cancel("known hunter can interrupt power acquisition", now, True)
            return None
        if distance(me["pos"], current["progress_pos"]) >= 2:
            current["progress_pos"], current["progress_at"] = tuple(me["pos"]), now
        elif now-current["progress_at"] > 3:
            self.cancel("opening mission made no progress", now, True)
            return None
        waypoint = self._route(me, goal, circle)
        if waypoint is False:
            self.cancel("bounded ground route cannot reach the mission", now, True)
            return None
        if waypoint is None:
            self.state, self.reason, self.plan = "planning", "continue bounded ground route", None
            return None
        self.state = current["phase"]
        self.reason = "secure selected "+current["kind"]+" then collect its actual reward"
        self.plan = Mission(tuple(goal), "collect" if current["phase"] == "collect" else current["kind"],
            target_id, exclusive, me["energy"] > self.ENERGY_RESERVE+15 and distance(me["pos"], goal) > 10,
            self.reason, waypoint)
        return self.plan

    def scan_yaw(self, obs, threats):
        """Fast quiet scan, only used by a caller with no mission or hostile aim."""
        if obs["t"] >= self.START_UNTIL:
            return None
        self.update(obs)
        me, now = obs["self"], obs["t"]
        if (self.current is not None or now >= self.START_UNTIL or not me["in_zone"] or
                me["hp"] < me["max_hp"]*.90 or now-self.last_hit < 2.5 or
                self._pressure(obs, threats, .5)):
            return None
        return (me["aim"][0]+me["stats"]["turn_rate"]*.1*.95+math.pi)%math.tau-math.pi
