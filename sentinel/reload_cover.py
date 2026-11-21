"""Use the unavoidable empty-magazine interval to step behind nearby cover."""
from dataclasses import dataclass
import math
import time

from .cover import firing_lane
from .geometry import distance, unit
from .movement import forecast


@dataclass(frozen=True)
class ReloadMove:
    move: tuple
    goal: tuple


class ReloadCover:
    def __init__(self, config):
        self.config = config
        self.goal = None
        self.target_id = None
        self.valid_until = -1

    def cancel(self):
        self.goal, self.target_id = None, None
        return None

    def _usable_secondary(self, me, opponent, reload_left):
        d = distance(me["pos"], opponent["pos"])
        for weapon in me["weapons"]:
            if not weapon or weapon["kind"] == "gun":
                continue
            kind, stats = weapon["kind"], weapon["stats"]
            if kind == "laser" and (weapon.get("charge", 0) > 0 or
                    (d <= stats["range"] and weapon.get("cooldown", 0) < reload_left-.15)):
                return True
            if kind == "lightning" and d <= stats["range"]+4 and me["energy"] > stats["energy"]+12:
                return True
            if kind == "mortar" and 19 < d < 170 and weapon.get("cooldown", 0) < reload_left-.15:
                return True
        return False

    def _world_point(self, world, xy, me, circle):
        stats = me["stats"]
        point = (*xy[:2], world.ground(*xy[:2]))
        if (distance(point, circle[0])+6 >= circle[1] or
                not world.body_clear(*point, stats["radius"]+.35, stats["height"], stats["step_up"]) or
                not world.walk_clear(me["pos"], point, stats["radius"]+.35, stats["height"],
                                     stats["step_up"], stats["max_slope_deg"])):
            return None
        return point

    def choose(self, obs, target, threats, circle, shelter):
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        gun = next((weapon for weapon in me["weapons"] if weapon and weapon["kind"] == "gun"), None)
        if gun is None or not me["grounded"] or not me["in_zone"]:
            return self.cancel()
        if gun.get("reload", 0) > 0:
            reload_left = gun["reload"]
        elif gun.get("ammo", 0) <= 0:
            reload_left = gun["stats"]["reload"]
        else:
            return self.cancel()
        if self.target_id is not None:
            target = next((enemy for enemy in obs["mechs"] if enemy["id"] == self.target_id), None)
        if (target is None or me["hp"] < .40*me["max_hp"] or
                not 29 < distance(p, target["pos"]) < 150 or self._usable_secondary(me, target, reload_left) or
                any(e["id"] != target["id"] and c >= .4 and distance(p, e["pos"]) < 110 for e, c in threats)):
            return self.cancel()
        world = shelter.world
        if abs(p[2]-world.ground(*p[:2])) > stats["step_up"]+.5:
            return self.cancel()

        def screened(point):
            return not firing_lane(world, self.config, point, me, target)[0]

        if self.goal is not None:
            point = self._world_point(world, self.goal, me, circle)
            if now >= self.valid_until or point is None or not screened(point):
                return self.cancel()
        elif reload_left > 1.05 and not screened(p):
            max_distance = min(19, stats["walk_speed"]*(reload_left-.65))
            deadline = time.perf_counter()+.003
            point, best = None, math.inf
            for xy in shelter._anchors(me):
                if time.perf_counter() >= deadline:
                    break
                d = distance(p, xy)
                if d >= min(best, max_distance):
                    continue
                candidate = self._world_point(world, xy, me, circle)
                if candidate is not None and screened(candidate):
                    point, best = candidate, d
            if point is None:
                return self.cancel()
            self.goal, self.target_id = point, target["id"]
            self.valid_until = now+reload_left+.2
        else:
            return None

        brake = forecast(me, (0, 0), stats["walk_speed"], .3)
        if screened(p) and screened(brake) and distance(p, point) < 4:
            return ReloadMove((0, 0), point)
        delta = (point[0]-p[0], point[1]-p[1])
        speed_fraction = min(1, max(.25, math.hypot(*delta)/5))
        move = unit(*delta)
        return ReloadMove((move[0]*speed_fraction, move[1]*speed_fraction), point)
