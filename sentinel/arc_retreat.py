"""Finish a laser cycle along a coherent safe corridor outside a closing arc.

This owns only a short ground movement direction. Weapons, targets, boost and
health policy remain with the normal Bot. Each observation checks the live
body, storm, known attackers and incoming rounds before retaining the direction.
"""
import math
import time

from .cover import firing_lane
from .geometry import distance, unit


class ArcRetreat:
    MAX_SECONDS = .003

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.direction = None
        self.enemy_id = None
        self.phase = None
        self.until = -1
        self.danger_until = -1
        self.reason = "no imminent arc-entry threat"

    def cancel(self, reason):
        self.direction = self.enemy_id = self.phase = None
        self.until = -1
        self.reason = reason

    @staticmethod
    def _forecast(me, direction, seconds, speed):
        position, velocity = list(me["pos"]), list(me["vel"][:2])
        path = [position]
        for _ in range(max(1, math.ceil(seconds/.05))):
            change = [direction[i]*speed-velocity[i] for i in range(2)]
            fraction = min(1, me["stats"]["ground_accel"]*.05/max(1e-9, math.hypot(*change)))
            velocity = [velocity[i]+change[i]*fraction for i in range(2)]
            position = [position[i]+velocity[i]*.05 for i in range(2)]+[me["pos"][2]]
            path.append(position)
        return path

    def _charge_safe(self, me, enemy, laser, direction, ordinary):
        left = max(.10, laser["stats"]["charge"]-laser.get("charge", 0))+.05
        speed = me["stats"]["walk_speed"]*me["stats"]["charge_move_mult"]
        forecasts = [self._forecast(me, move, left, speed) for move in (direction, ordinary)]
        minima = []
        for path in forecasts:
            minima.append(min(distance(point, [enemy["pos"][i]+enemy.get("vel", [0, 0, 0])[i]*j*.05
                                              for i in range(3)]) for j, point in enumerate(path)))
        arc = self.config["weapons"]["lightning"]["range"]
        enemy_radius = self.config["mech"]["radius"]*(1+
            self.config["cubes"].get("size_per_cube", .05)*enemy.get("cubes", 0))
        return minima[0] > arc+1 and minima[1] <= arc+me["stats"]["radius"]+enemy_radius+1

    def _contacts(self, obs, path):
        me, contacts = obs["self"], set()
        for index, projectile in enumerate(obs["projectiles"]):
            gravity = self.config["weapons"]["mortar"]["gravity"] if projectile["kind"] == "mortar" else 0
            splash = self.config["weapons"]["mortar"]["splash_radius"] if gravity else 0
            radius = me["stats"]["radius"]+.3+splash
            for j, (a, b) in enumerate(zip(path[:6], path[1:7])):
                start, end = j*.05, (j+1)*.05
                p = [projectile["pos"][i]+projectile["vel"][i]*start for i in range(3)]
                q = [projectile["pos"][i]+projectile["vel"][i]*end for i in range(3)]
                p[2] -= gravity*start*start/2
                q[2] -= gravity*end*end/2
                x, y = p[0]-a[0], p[1]-a[1]
                dx, dy = q[0]-b[0]-x, q[1]-b[1]-y
                t = max(0, min(1, -(x*dx+y*dy)/(dx*dx+dy*dy or 1)))
                z = p[2]+(q[2]-p[2])*t
                feet = a[2]+(b[2]-a[2])*t
                if math.hypot(x+dx*t, y+dy*t) <= radius and feet-1 <= z <= feet+me["stats"]["height"]+1:
                    contacts.add(projectile.get("id", index))
                    break
        return contacts

    def choose(self, obs, move, boost, *, circle, fire, active_ids, threats=(), reserved=False):
        deadline = time.perf_counter()+self.MAX_SECONDS
        me, now = obs["self"], obs["t"]
        candidates = [enemy for enemy in obs["mechs"] if enemy.get("kind") == "mech" and
                      enemy["id"] in active_ids and "lightning" in enemy.get("weapons", ())]
        enemy = next((enemy for enemy in candidates if enemy["id"] == self.enemy_id),
                     min(candidates, key=lambda enemy: distance(me["pos"], enemy["pos"]), default=None))
        if any(event["type"] == "damaged" and event.get("amount", 0) > 0 and
               event.get("weapon") != "zone" and (not enemy or event.get("by") != enemy["id"])
               for event in obs["events"]):
            self.danger_until = now+1
        lasers = [(slot, weapon) for slot, weapon in enumerate(me["weapons"])
                  if weapon and weapon["kind"] == "laser"]
        slot, laser = lasers[0] if lasers else (0, None)
        if (reserved or boost or not enemy or not laser or not me["grounded"] or not me["in_zone"] or
                now < self.danger_until or len(obs["projectiles"]) > 16 or
                abs(me["pos"][2]-self.world.ground(*me["pos"][:2])) > me["stats"]["step_up"]+.5 or
                any(other.get("kind") == "npc" and distance(me["pos"], other["pos"]) < 90
                    for other in obs["mechs"])):
            self.cancel("another controller, pressure, or terrain owns movement")
            return move, boost
        gap = distance(me["pos"], enemy["pos"])
        away = unit(me["pos"][0]-enemy["pos"][0], me["pos"][1]-enemy["pos"][1])
        closing = sum(enemy.get("vel", [0, 0, 0])[i]*away[i] for i in range(2))
        enemy_radius = self.config["mech"]["radius"]*(1+
            self.config["cubes"].get("size_per_cube", .05)*enemy.get("cubes", 0))
        body_spacing = me["stats"]["radius"]+enemy_radius+3
        minimum = body_spacing if self.direction else max(46, body_spacing)
        if gap <= minimum or gap >= (70 if self.direction else 64) or closing < 3 or not firing_lane(
                self.world, self.config, me["pos"], me, enemy)[0]:
            self.cancel("arc is already too close, safely distant, or no longer pursuing")
            return move, boost
        observed = {other["id"]: other for other, confidence in threats if confidence >= .45}
        observed.update({other["id"]: other for other in obs["mechs"] if other.get("kind") == "mech"})
        for other in observed.values():
            if other["id"] != enemy["id"] and distance(me["pos"], other["pos"]) < 280 and firing_lane(
                    self.world, self.config, me["pos"], me, other)[0]:
                self.cancel("second exposed attacker invalidates the corridor")
                return move, boost
        norm = math.hypot(*move)
        ordinary = [value/max(1, norm) for value in move]
        charging = laser.get("charge", 0) > 0 or (fire[slot] and laser.get("cooldown", 0) <= .15)
        start = self.direction is None
        if start:
            if (not charging or norm < .4 or sum(ordinary[i]*away[i] for i in range(2)) < .3 or
                    not self._charge_safe(me, enemy, laser, away, ordinary)):
                self.cancel("a coherent charge is unnecessary or cannot remain outside arc range")
                return move, boost
            self.phase, self.direction, self.enemy_id = "charge", list(away), enemy["id"]
            self.until = -1
        elif self.phase == "cooldown" and charging:
            # The existing Bot still controls the trigger. Losing clearance for
            # another beam is a reason to keep retreating, not to reintroduce
            # the lateral direction changes that let the arc catch us.
            self.phase = "charge"
        if self.phase == "charge" and not charging and laser.get("cooldown", 0) > .15:
            self.phase = "cooldown"
        if now >= self.until:
            self.direction = list(away)
            self.until = now+max(.3, min(1, (max(0, laser["stats"]["charge"]-laser.get("charge", 0))+.2)
                if charging else laser.get("cooldown", 0)+.1))
        if sum(self.direction[i]*away[i] for i in range(2)) < .75:
            self.cancel("pursuer changed the corridor bearing")
            return move, boost
        paths, normals = [], []
        for multiplier in (1, me["stats"]["charge_move_mult"]):
            path = self._forecast(me, self.direction, max(.35, self.until-now), me["stats"]["walk_speed"]*multiplier)
            normal = self._forecast(me, ordinary, .3, me["stats"]["walk_speed"]*multiplier)
            for point in path:
                point[2] = self.world.ground(*point[:2])
                if distance(point, circle[0])+me["stats"]["radius"]+3 >= circle[1]:
                    self.cancel("future storm blocks the retreat corridor")
                    return move, boost
            enemy_radius = self.config["mech"]["radius"]*(1+
                self.config["cubes"].get("size_per_cube", .05)*enemy.get("cubes", 0))
            for index, point in enumerate(path):
                future = [enemy["pos"][i]+enemy.get("vel", [0, 0, 0])[i]*index*.05 for i in range(3)]
                if distance(point, future) < me["stats"]["radius"]+enemy_radius+.3:
                    self.cancel("pursuer body can reach the retreat corridor")
                    return move, boost
            for a, b in zip(path, path[1:]):
                if time.perf_counter() >= deadline or not self.world.walk_clear(a, b,
                        me["stats"]["radius"]+.3, me["stats"]["height"],
                        me["stats"]["step_up"], me["stats"]["max_slope_deg"]):
                    self.cancel("body clearance or work budget rejects the corridor")
                    return move, boost
            for point in normal:
                point[2] = self.world.ground(*point[:2])
            paths.append(path)
            normals.append(normal)
        proposed = self._contacts(obs, paths[0]) | self._contacts(obs, paths[1])
        ordinary_hits = self._contacts(obs, normals[0]) & self._contacts(obs, normals[1])
        if proposed-ordinary_hits or time.perf_counter() >= deadline:
            self.cancel("a visible projectile needs the ordinary dodge")
            return move, boost
        self.reason = "retain one checked direction through the laser cycle"
        return list(self.direction), boost
