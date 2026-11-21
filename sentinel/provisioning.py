"""Commit to free equipment only along a certified, short protected corridor."""
from dataclasses import dataclass
import math
import time

from .cover import firing_lane
from .geometry import distance


@dataclass(frozen=True)
class ResourcePlan:
    goal: tuple
    kind: str
    item_id: int
    arming: bool


class Provisioner:
    MAX_DISTANCE = 45
    MAX_CANDIDATES = 6
    SEARCH_SECONDS = .003
    SAMPLE_SPACING = 4
    VALUES = {"gun": 0, "mortar": 1, "laser": 3, "lightning": 3}

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.plan = None
        self.state = "idle"
        self.reason = "no secured resource"
        self.equipping_kind = None
        self.last_second_kind = None
        self.saw_self = False
        self.rays = 0
        self.samples = 0

    def _ground_item(self, item, me, circle):
        p = item["pos"]
        if abs(p[2]-self.world.ground(*p[:2])) >= 4:
            return False
        margin = me["stats"]["radius"]+5
        if distance(p, circle[0]) >= circle[1]-margin:
            return False
        return self.world.body_clear(p[0], p[1], self.world.ground(*p[:2]),
                                     me["stats"]["radius"]+.3,
                                     me["stats"]["height"], me["stats"]["step_up"])

    def _projectile_crosses(self, point, me, projectile):
        """Conservative continuous horizontal crossing, with vertical bounds.

        Fast bullets can traverse the whole corridor between discrete snapshots.
        Mortar height is bounded over short parabolic intervals, including apex.
        """
        position, velocity = projectile["pos"], projectile["vel"]
        mortar = projectile["kind"] == "mortar"
        gravity = self.config["weapons"]["mortar"]["gravity"] if mortar else 0
        radius = me["stats"]["radius"]+3
        if mortar:
            radius += self.config["weapons"]["mortar"]["splash_radius"]
        segments = 8 if mortar else 1
        for i in range(segments):
            start, end = .75*i/segments, .75*(i+1)/segments
            heights = [position[2]+velocity[2]*t-gravity*t*t/2 for t in (start, end)]
            if gravity and start < velocity[2]/gravity < end:
                apex = velocity[2]/gravity
                heights.append(position[2]+velocity[2]*apex-gravity*apex*apex/2)
            if max(heights) <= point[2]-3 or min(heights) >= point[2]+me["stats"]["height"]+3:
                continue
            rx, ry = position[0]-point[0], position[1]-point[1]
            squared = velocity[0]*velocity[0]+velocity[1]*velocity[1]
            closest = max(start, min(end, -(rx*velocity[0]+ry*velocity[1])/(squared or 1)))
            if math.hypot(rx+velocity[0]*closest, ry+velocity[1]*closest) < radius:
                return True
        return False

    def _corridor(self, obs, goal, enemies, deadline):
        me = obs["self"]
        stats, start = me["stats"], me["pos"]
        ground = self.world.ground(*start[:2])
        if start[2]-ground > stats["step_up"]+.5:
            return False
        end = (*goal, self.world.ground(*goal))
        if time.perf_counter() >= deadline or not self.world.walk_clear(
                start, end, stats["radius"]+.3, stats["height"],
                stats["step_up"], stats["max_slope_deg"]):
            return False
        # NPC attack state is not observed. Conservatively decline a special
        # free-loot override inside any visible drone's possible chase radius.
        dx, dy = goal[0]-start[0], goal[1]-start[1]
        squared = dx*dx+dy*dy
        for npc in obs["mechs"]:
            if npc.get("kind") != "npc":
                continue
            fraction = max(0, min(1, ((npc["pos"][0]-start[0])*dx+
                                      (npc["pos"][1]-start[1])*dy)/(squared or 1)))
            nearest = (start[0]+dx*fraction, start[1]+dy*fraction)
            if distance(nearest, npc["pos"]) < self.config["npc"]["deaggro_range"]:
                return False
        steps = max(1, math.ceil(distance(start, goal)/self.SAMPLE_SPACING))
        for i in range(steps+1):
            fraction = i/steps
            x, y = start[0]+(goal[0]-start[0])*fraction, start[1]+(goal[1]-start[1])*fraction
            point = (x, y, self.world.ground(x, y))
            self.samples += 1
            for projectile in obs["projectiles"]:
                if time.perf_counter() >= deadline:
                    return False
                if self._projectile_crosses(point, me, projectile):
                    return False
            for enemy, _ in enemies:
                if time.perf_counter() >= deadline:
                    return False
                exposed, rays = firing_lane(self.world, self.config, point, me, enemy)
                self.rays += rays
                if exposed:
                    return False
        return time.perf_counter() < deadline

    def choose(self, obs, loot, threats, circle, recovering=False):
        """Return a certified cube/weapon plan, or fail closed without a plan.

        A direct corridor is intentional: this module never starts an A* search
        for each item or assumes an endpoint behind a wall implies a safe route.
        The caller retains zone, escape, and committed shelter approach priority.
        """
        me = obs["self"]
        previous = self.plan
        self.plan = None
        self.rays = self.samples = 0
        second = me["weapons"][1]
        second_kind = second["kind"] if second else None
        if self.saw_self and second_kind is not None and second_kind != self.last_second_kind:
            self.equipping_kind = second_kind
        self.last_second_kind, self.saw_self = second_kind, True
        if second and second["kind"] == self.equipping_kind:
            if second.get("cooldown", 0) > 0:
                self.state, self.reason = "equipping", "wait for acquired secondary to be ready"
                return None
            self.equipping_kind = None
        held = {w["kind"] for w in me["weapons"] if w}
        current = self.VALUES.get(second["kind"], 0) if second else 0
        weapons = [item for item in loot.get("pickups")
                   if item["kind"] not in held and item["kind"] != "gun"
                   and self.VALUES.get(item["kind"], 0) > current+.5
                   and distance(me["pos"], item["pos"]) <= self.MAX_DISTANCE
                   and self._ground_item(item, me, circle)]
        candidates = [("weapon", item) for item in weapons
                      if distance(me["pos"], item["pos"]) <= self.MAX_DISTANCE]
        if me["cubes"] < self.config["cubes"].get("stat_cap", 10):
            candidates += [("cube", item) for item in loot.get("cubes")
                           if distance(me["pos"], item["pos"]) <= self.MAX_DISTANCE
                           and self._ground_item(item, me, circle)]
        # Preserve an approved commitment while it is still safe. Otherwise arm
        # before collecting cubes when slot 1 is empty, then minimize travel.
        candidates.sort(key=lambda pair: (
            not (previous and previous.item_id == pair[1]["id"]),
            second is None and pair[0] != "weapon", distance(me["pos"], pair[1]["pos"])))
        enemies = [(enemy, confidence) for enemy, confidence in threats
                   if enemy.get("kind") == "mech" and confidence >= .25
                   and distance(me["pos"], enemy["pos"]) <= 350]
        deadline = time.perf_counter()+self.SEARCH_SECONDS
        for kind, item in candidates[:self.MAX_CANDIDATES]:
            if time.perf_counter() >= deadline:
                break
            goal = tuple(item["pos"][:2])
            if self._corridor(obs, goal, enemies, deadline):
                arming = kind == "weapon" and second is None
                self.plan = ResourcePlan(goal, kind, item["id"], arming)
                self.state = "arming" if arming else "collect"
                self.reason = "certified protected free-resource corridor"
                return self.plan
        self.state, self.reason = "idle", "no certified free-resource corridor"
        if second is None:
            self.equipping_kind = None
        return None

    def defer_duel(self, obs, duel):
        """Gun-only readiness doctrine, independent of pickup memory or plans.

        Keep ordinary defensive firing and risk-scored goals, but do not adopt
        the 65m closing posture against an opponent carrying a secondary.
        """
        if duel is None or obs["alive"] <= 2:
            return False
        if duel.get("hp", 1400) < 170 and distance(obs["self"]["pos"], duel["pos"]) <= 28:
            return False
        unarmed = obs["self"]["weapons"][1] is None
        armed_enemy = any(kind != "gun" for kind in duel.get("weapons", []))
        return (unarmed or self.state == "equipping") and armed_enemy

    def selected_weapon_objective(self, obs, loot, circle, objective, goal):
        """Recognize the existing mission without certifying or forcing its route.

        This only preserves normal risk scoring while changing combat posture;
        it never grants the protected free-resource override.
        """
        if not objective or goal is None:
            return False
        category, item_id, expires = objective
        if category != "pickups" or obs["t"] >= expires:
            return False
        held = {w["kind"] for w in obs["self"]["weapons"] if w}
        return any(item["id"] == item_id and item["kind"] not in held and
                   item["kind"] != "gun" and distance(item["pos"], goal) < 1 and
                   self._ground_item(item, obs["self"], circle)
                   for item in loot.get("pickups"))
