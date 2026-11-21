"""Bounded physical fallback for a ready mortar rejected by the angular gate.

The original solver and normally aligned shots stay with Combat. This fallback
requires both plausible launch orientations to contact the same moving body;
an unreachable ready mortar periodically yields the shared torso to the gun.
"""
from dataclasses import dataclass
import math
import time

from .geometry import angle_error, distance


@dataclass(frozen=True)
class Decision:
    extra_fire: bool
    handoff_gun: bool
    reason: str


class MortarFallback:
    TRACE_SECONDS = .003
    MAX_FLIGHT = 2.0
    MAX_DISTANCE = 110.0
    REJECTIONS = 3
    GUN_DECISIONS = 4

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.target_id = None
        self.rejected = 0
        self.gun_left = 0
        self.reason = "ordinary mortar controller"

    def _body(self, target):
        if target.get("kind") == "mech":
            scale = 1+self.config["cubes"]["size_per_cube"]*target.get("cubes", 0)
            return self.config["mech"]["radius"]*scale, self.config["mech"]["height"]*scale
        return self.config["npc"]["radius"], self.config["npc"]["height"]

    @staticmethod
    def _horizontal_interval(a, b, radius):
        dx, dy = b[0]-a[0], b[1]-a[1]
        aa, bb, cc = dx*dx+dy*dy, 2*(a[0]*dx+a[1]*dy), a[0]**2+a[1]**2-radius*radius
        if aa < 1e-12:
            return (0, 1) if cc <= 0 else None
        disc = bb*bb-4*aa*cc
        if disc < 0:
            return None
        root = math.sqrt(disc)
        lo, hi = max(0, (-bb-root)/(2*aa)), min(1, (-bb+root)/(2*aa))
        return (lo, hi) if lo <= hi else None

    def _trace(self, me, target, mortar, aim, delay, deadline):
        stats, weapon = me["stats"], mortar["stats"]
        feet = [me["pos"][i]+me["vel"][i]*delay for i in range(3)]
        feet[2] = self.world.ground(*feet[:2])
        muzzle = [feet[0], feet[1], feet[2]+stats["height"]+.5]
        direction = [math.cos(aim[1])*math.cos(aim[0]),
                     math.cos(aim[1])*math.sin(aim[0]), math.sin(aim[1])]
        origin = [muzzle[i]+direction[i]*(stats["radius"]+.5) for i in range(3)]
        if not self.world.line_clear(muzzle, origin):
            return False
        radius, height = self._body(target)
        radius = max(.1, radius-.2)
        velocity = target.get("vel", [0, 0, 0])
        previous = origin
        for step in range(1, math.ceil(self.MAX_FLIGHT/.05)+1):
            if time.perf_counter() >= deadline:
                return False
            start, end = (step-1)*.05, step*.05
            point = [origin[0]+direction[0]*weapon["speed"]*end,
                     origin[1]+direction[1]*weapon["speed"]*end,
                     origin[2]+direction[2]*weapon["speed"]*end-weapon["gravity"]*end*end/2]
            before_body = [target["pos"][i]+velocity[i]*(delay+start) for i in range(3)]
            after_body = [target["pos"][i]+velocity[i]*(delay+end) for i in range(3)]
            relative_a = [previous[i]-before_body[i] for i in range(2)]
            relative_b = [point[i]-after_body[i] for i in range(2)]
            interval = self._horizontal_interval(relative_a, relative_b, radius)
            if interval:
                # An interior point is sufficient to prove a contact. The
                # short segment's exact parabolic height avoids cap grazes.
                for fraction in (interval[0], sum(interval)/2, interval[1]):
                    flight = start+(end-start)*fraction
                    contact = [origin[0]+direction[0]*weapon["speed"]*flight,
                               origin[1]+direction[1]*weapon["speed"]*flight,
                               origin[2]+direction[2]*weapon["speed"]*flight-
                               weapon["gravity"]*flight*flight/2]
                    body_z = target["pos"][2]+velocity[2]*(delay+flight)
                    if not body_z+.2 <= contact[2] <= body_z+height-.2:
                        continue
                    own_future = [me["pos"][i]+me["vel"][i]*(delay+flight) for i in range(2)]
                    if distance(contact, own_future) <= weapon.get("splash_radius", 7)+stats["radius"]+2:
                        return False
                    return self.world.line_clear(previous, contact)
            if point[2] <= self.world.ground(*point[:2]) or not self.world.line_clear(previous, point):
                return False
            previous = point
        return False

    def assess(self, me, target, mortar, commanded_aim, *, legacy_aligned=False):
        key = target.get("id")
        if key != self.target_id:
            self.target_id, self.rejected, self.gun_left = key, 0, 0
        if legacy_aligned:
            self.rejected = self.gun_left = 0
            return Decision(False, False, "preserve ordinary aligned mortar")
        ready = mortar.get("cooldown", 0) <= .001
        stable = (me.get("grounded", True) and abs(target.get("vel", [0, 0, 0])[2]) <= .5 and
                  abs(me["pos"][2]-self.world.ground(*me["pos"][:2])) <= me["stats"]["step_up"]+.5 and
                  target.get("kind") in ("mech", "npc") and
                  self.config["weapons"]["mortar"]["splash_radius"]+9 <= distance(me["pos"], target["pos"]) <= self.MAX_DISTANCE)
        valid = False
        if ready and stable:
            stats = me["stats"]
            current = me["aim"]
            yaw_step = max(-stats["turn_rate"]*.05, min(stats["turn_rate"]*.05,
                           angle_error(commanded_aim[0], current[0])))
            pitch_step = max(-stats["pitch_rate"]*.05, min(stats["pitch_rate"]*.05,
                             commanded_aim[1]-current[1]))
            future = [current[0]+yaw_step, current[1]+pitch_step]
            deadline = time.perf_counter()+self.TRACE_SECONDS
            valid = (self._trace(me, target, mortar, current, 0, deadline) and
                     self._trace(me, target, mortar, current, .05, deadline) and
                     self._trace(me, target, mortar, future, .05, deadline))
        if valid:
            self.rejected = self.gun_left = 0
            self.reason = "both current and next launch arcs hit the live body"
            return Decision(True, False, self.reason)
        gun = next((weapon for weapon in me["weapons"] if weapon and weapon["kind"] == "gun" and
                    weapon.get("ammo", 0) > 0 and weapon.get("reload", 0) <= 0), None)
        if not ready or gun is None:
            self.rejected = 0
            return Decision(False, False, "preserve ordinary unready mortar or unavailable gun")
        if self.gun_left:
            self.gun_left -= 1
            return Decision(False, True, "retain the short gun acquisition window")
        self.rejected += 1
        if self.rejected >= self.REJECTIONS:
            self.rejected = 0
            self.gun_left = self.GUN_DECISIONS-1
            return Decision(False, True, "unreachable mortar yields four decisions to gun")
        return Decision(False, False, "brief mortar acquisition before gun handoff")
