"""Short laser trades from a measured corner, using only public geometry.

The return value owns aim/triggers and, except during approach, ground movement.
No hypothetical damage is scored: a shot is released only on current torso aim
and an actual clear muzzle ray. Failed trades return to the verified hiding side.
"""
import math
import time

from .combat import aim_at, target_center
from .cover import firing_lane
from .geometry import angle_error, distance, unit


class AmbushPlanner:
    MAX_CANDIDATES = 12
    SEARCH_SECONDS = .0035
    CELL = 48

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.corners = {}
        for prism in world.prisms:
            for a, b in prism.all_edges:
                length = distance(a, b)
                if length < 9:
                    continue
                tx, ty = (b[0]-a[0])/length, (b[1]-a[1])/length
                for corner, ix, iy in ((a, tx, ty), (b, -tx, -ty)):
                    for sign in (-1, 1):
                        record = (corner, ix, iy, -iy*sign, ix*sign)
                        key = (math.floor(corner[0]/self.CELL), math.floor(corner[1]/self.CELL))
                        self.corners.setdefault(key, []).append(record)
        self.state, self.reason = "idle", "no corner trade"
        self.hide = self.peek = self.goal = None
        self.target_id = None
        self.target = None
        self.seen = {}
        self.beam_at = {}
        self.next_search = -1
        self.deadline = self.progress_at = -1
        self.progress_position = None
        self.escape_until = -1
        self.needs_escape = False
        self.candidates = self.rays = 0
        self.release_at = -1
        self.charge_auto_at = -1
        self.abort_reason = None
        self.body = None

    def clear(self, reason="corner trade complete"):
        self.state, self.reason = "idle", reason
        self.hide = self.peek = self.goal = None
        self.target_id = None
        self.target = None
        self.progress_position = None
        self.abort_reason = None

    def _point(self, xy, me, circle):
        radius, height = me["stats"]["radius"], me["stats"]["height"]
        if distance(xy, circle[0]) > circle[1]-radius-3:
            return None
        p = (*xy[:2], self.world.ground(*xy[:2]))
        if not self.world.body_clear(*p, radius+.35, height,
                                     me["stats"].get("step_up", 1.2)):
            return None
        return p

    def _walk(self, a, b, me):
        s = me["stats"]
        return self.world.walk_clear(a, b, s["radius"]+.35, s["height"],
                                     s.get("step_up", 1.2), s.get("max_slope_deg", 50))

    def _covered(self, p, me, enemies):
        for enemy, _ in enemies:
            visible, rays = firing_lane(self.world, self.config, p, me, enemy)
            self.rays += rays
            if visible:
                return False
        return True

    def _aim(self, p, me, enemy):
        origin = [p[0], p[1], p[2]+me["stats"]["muzzle_height"]]
        center, radius, height = target_center(enemy, self.config)
        return aim_at(origin, center), origin, center, radius, height

    def _can_shoot(self, p, me, enemy, laser, actual=False):
        desired, origin, center, radius, height = self._aim(p, me, enemy)
        if math.dist(origin, center) > laser["stats"]["range"]:
            return False
        if not me["stats"].get("min_pitch", -.7) <= desired[1] <= me["stats"].get("max_pitch", 1.3):
            return False
        if not self.world.line_clear(origin, center):
            return False
        if not actual:
            return True
        # Test the actual ray as well as angular tolerance. Near a corner a
        # slightly misaligned ray can strike the wall despite a clear desired ray.
        yaw, pitch = me["aim"]
        d = math.dist(origin, center)
        ray = (origin[0]+math.cos(yaw)*math.cos(pitch)*d,
               origin[1]+math.sin(yaw)*math.cos(pitch)*d,
               origin[2]+math.sin(pitch)*d)
        horizontal = max(1, distance(p, enemy["pos"]))
        return (abs(angle_error(desired[0], yaw)) < math.atan2(radius*.85, horizontal)
                and abs(desired[1]-pitch) < math.atan2(height*.40, horizontal)
                and self.world.line_clear(origin, ray))

    def _travel(self, me, meters, charging=False):
        speed = me["stats"]["boost_speed"]
        if charging:
            speed *= me["stats"].get("charge_move_mult", .5)
        # Acceleration, braking and a decision boundary are included. Actual
        # progress, not this optimistic schedule, controls the state machine.
        return meters/max(1, speed)+.22

    def _rounding(self, me, enemy, hide, laser):
        # Straight-line distance is a conservative lower bound on rounding time.
        # Use the published boost speed, not a stationary enemy's current speed.
        speed = max(self.config["mech"]["boost_speed"], math.hypot(*enemy.get("vel", [0, 0])[:2]))
        separation = distance(enemy["pos"], hide)-me["stats"]["radius"]-3
        arrival = max(0, separation)/max(1, speed)
        charge_left = max(0, laser["stats"]["charge"]-laser.get("charge", 0))
        outward = distance(hide, self.peek or hide)
        if self.state == "peek":
            outward = distance(me["pos"], self.peek)
        cycle = (charge_left+.15+self._travel(me, outward, True)+
                 self._travel(me, distance(hide, self.peek or hide))+.35)
        if self.state == "approach":
            cycle += distance(me["pos"], hide)/max(1, me["stats"]["walk_speed"])
        return arrival < cycle

    def _beam_threat(self, obs, enemy):
        # A visible enemy beam supplies a real cooldown window; charging flags
        # alone never tell us how close the opponent is to releasing a beam.
        if not enemy.get("charging"):
            return False
        # A fresh current charging flag wins over inferred cooldown: enemy
        # upgrades are not known, so a beam timestamp cannot override it.
        return True

    def _search(self, me, enemy, enemies, circle, laser):
        p, radius = me["pos"], me["stats"]["radius"]
        cx, cy = math.floor(p[0]/self.CELL), math.floor(p[1]/self.CELL)
        records = []
        for j in range(cy-1, cy+2):
            for i in range(cx-1, cx+2):
                for corner, tx, ty, nx, ny in self.corners.get((i, j), ()):
                    hide = (corner[0]+tx*(radius+4)+nx*(radius+.8),
                            corner[1]+ty*(radius+4)+ny*(radius+.8))
                    if distance(p, hide) <= 20:
                        peek = (corner[0]-tx*(radius+.7)+nx*(radius+.8),
                                corner[1]-ty*(radius+.7)+ny*(radius+.8))
                        records.append((distance(p, hide)+distance(peek, enemy["pos"])*.01,
                                        hide, peek))
        records.sort(key=lambda r: r[0])
        end = time.perf_counter()+self.SEARCH_SECONDS
        for _, hidden, firing in records[:self.MAX_CANDIDATES]:
            if time.perf_counter() >= end:
                break
            self.candidates += 1
            hide, peek = self._point(hidden, me, circle), self._point(firing, me, circle)
            if hide is None or peek is None or distance(hide, peek) > 14:
                continue
            if (not self._walk(p, hide, me) or not self._walk(hide, peek, me)
                    or not self._covered(hide, me, enemies)
                    or not self._can_shoot(peek, me, enemy, laser)):
                continue
            # The hide is shared protection. The firing point must expose only
            # the selected target, not an untracked second attack lane.
            if not self._covered(peek, me, [(e, c) for e, c in enemies if e["id"] != enemy["id"]]):
                continue
            self.peek = peek
            if self._rounding(me, enemy, hide, laser):
                self.peek = None
                continue
            cost = (self._travel(me, distance(hide, peek), True)+
                    self._travel(me, distance(hide, peek)))*me["stats"]["boost_drain"]
            if me["energy"] < cost+30:
                self.peek = None
                continue
            return hide, peek
        return None

    def _motion(self, me, goal, boost):
        dx, dy = goal[0]-me["pos"][0], goal[1]-me["pos"][1]
        d = math.hypot(dx, dy)
        s = me["stats"]
        charged = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])
        speed = s["boost_speed"] if boost else s["walk_speed"]
        if charged:
            speed *= s.get("charge_move_mult", .5)
        # Analog velocity avoids oscillating across a corner arrival band. The
        # command compensates current inertia over a bounded .15-second window.
        desired_speed = min(speed, math.sqrt(max(0, 2*s["ground_accel"]*max(0, d-.25))), d/.16)
        ux, uy = unit(dx, dy)
        vx, vy = me["vel"][:2]
        factor = .10 if d > 1.5 else .18
        command = ((ux*desired_speed-factor*vx)/max(1, speed),
                   (uy*desired_speed-factor*vy)/max(1, speed))
        size = math.hypot(*command)
        return [command[0]/max(1, size), command[1]/max(1, size)]

    def _control(self, me, enemy, slot, laser, move=None, boost=False, hold=False):
        aim = self._aim(me["pos"], me, enemy)[0]
        aim[1] = max(me["stats"].get("min_pitch", -.7), min(me["stats"].get("max_pitch", 1.3), aim[1]))
        fire = [False, False]
        fire[slot] = bool(hold)
        return {"goal": tuple(self.goal[:2]), "move": move, "boost": boost,
                "aim": aim, "fire": fire}

    def _withdraw(self, obs, reason, escape=False):
        if escape:
            self.escape_until = max(self.escape_until, obs["t"]+6)
            self.needs_escape = True
        self.abort_reason = reason
        self.state, self.reason = "retreat", reason
        self.deadline = obs["t"]+3
        self.progress_at, self.progress_position = obs["t"], tuple(obs["self"]["pos"])

    def choose(self, obs, threats, circle, recovering=False):
        self.candidates = self.rays = 0
        me, now = obs["self"], obs["t"]
        self.needs_escape = now < self.escape_until
        for enemy in obs.get("mechs", ()):
            if enemy.get("kind") == "mech":
                self.seen[enemy["id"]] = (now, enemy)
        self.seen = {i: v for i, v in self.seen.items() if now-v[0] <= 1.0}
        for beam in obs.get("beams", ()):
            if beam["kind"] == "laser":
                self.beam_at[beam["by"]] = now-beam.get("age", 0)
        for event in obs.get("events", ()):
            if event["type"] == "kill":
                self.seen.pop(event["target"], None)
        lasers = [(i, w) for i, w in enumerate(me["weapons"]) if w and w["kind"] == "laser"]
        if not lasers or not me.get("grounded", True):
            self.clear("no grounded laser trade")
            return None
        slot, laser = lasers[0]
        body = (me["stats"]["radius"], me["stats"]["height"])
        enemies = sorted(((e, c) for e, c in threats if e.get("kind") == "mech" and c >= .4
                          and distance(me["pos"], e["pos"]) < 280),
                         key=lambda ec: distance(me["pos"], ec[0]["pos"]))[:15]
        tracked = self.seen.get(self.target_id) if self.target_id is not None else None
        enemy = tracked[1] if tracked else (self.target if self.state != "idle" else
                                           (enemies[0][0] if enemies else None))
        if tracked:
            self.target = enemy
        invalid = (recovering or not me.get("in_zone", True) or me["hp"] < me["max_hp"]*.70)
        if enemy is None:
            self.clear("target no longer tracked")
            return None
        if self.state == "idle":
            if (invalid or now < self.next_search or self.needs_escape or enemy["id"] not in self.seen
                    or laser.get("charge", 0) > 0 or me["energy"] < 65
                    or me["pos"][2] > self.world.ground(*me["pos"][:2])+1.5):
                return None
            self.next_search = now+.5
            pair = self._search(me, enemy, enemies, circle, laser)
            if pair is None:
                self.reason = "no measured protected firing pair"
                return None
            self.hide, self.peek = pair
            self.target_id, self.body = enemy["id"], body
            self.target = enemy
            self.state, self.reason = "approach", "approach measured firing corner"
            self.deadline = now+4
            self.progress_at, self.progress_position = now, tuple(me["pos"])

        # Live invariants are checked before state advancement. Retaining an old
        # corner after growth, zone change or a flanker would be a death trap.
        valid = (self._point(self.hide, me, circle) is not None
                 and self._point(self.peek, me, circle) is not None
                 and self._walk(me["pos"], self.hide, me)
                 and self._walk(self.hide, self.peek, me))
        hidden = valid and self._covered(self.hide, me, enemies)
        crossed = valid and not self._covered(self.peek, me, [(e, c) for e, c in enemies
                                                             if e["id"] != self.target_id])
        if not valid or not hidden:
            self.needs_escape = True
            self.escape_until = now+6
            self.clear("corner support, zone or shelter lost")
            return None
        if self.state != "retreat" and (invalid or crossed or body != self.body
                                         or self.target_id not in self.seen):
            self._withdraw(obs, "leave unsafe or stale trade", True)
        if self.state in ("approach", "charge", "cooldown", "peek") and self._rounding(me, enemy, self.hide, laser):
            self._withdraw(obs, "hunter can round before the next trade", True)
        if self.state != "retreat" and now > self.deadline:
            self._withdraw(obs, "corner phase deadline", True)
        if self.progress_position is None or distance(me["pos"], self.progress_position) > .8:
            self.progress_position, self.progress_at = tuple(me["pos"]), now
        if self.state in ("approach", "peek", "retreat") and now-self.progress_at > 1.2:
            if self.state == "retreat":
                self.escape_until = now+6
                self.needs_escape = True
                self.clear("corner withdrawal blocked")
                return None
            self._withdraw(obs, "corner movement made no progress", True)

        charge = laser.get("charge", 0)
        full = laser["stats"]["charge"]
        auto = full+laser["stats"].get("hold_s", 2)
        # Some observations may cap charge at full while the server's hold
        # clock continues. Bound the window from our own first trigger command
        # AND first observed full charge, never from charge alone.
        if charge >= full and self.charge_auto_at > 0:
            observed_deadline = now+laser["stats"].get("hold_s", 2)-.15-max(0, charge-full)
            self.charge_auto_at = min(self.charge_auto_at, observed_deadline)
        auto_left = self.charge_auto_at-now if self.charge_auto_at > 0 else auto-charge-.15
        d_hide, d_peek = distance(me["pos"], self.hide), distance(me["pos"], self.peek)
        if self.state == "approach":
            self.goal = self.hide
            if d_hide > .8 or math.hypot(*me["vel"][:2]) > 2:
                # Ordinary ground steering intentionally stops a couple meters
                # short of cover. Own the last three meters so charging does
                # not wait forever outside its narrower safe arrival band.
                move = self._motion(me, self.hide, False) if d_hide < 3 else None
                return self._control(me, enemy, slot, laser, move=move)
            self.state, self.reason = "cooldown", "wait behind cover for laser"
            self.deadline = now+max(3, laser.get("cooldown", 0)+1)
        if self.state == "cooldown":
            self.goal = self.hide
            if laser.get("cooldown", 0) > .02:
                return self._control(me, enemy, slot, laser, self._motion(me, self.hide, False))
            if me["energy"] < 60:
                self.clear("retain escape energy after trade")
                return None
            self.state, self.reason = "charge", "charge laser behind verified cover"
            self.deadline = now+auto+.3
            self.charge_auto_at = now+auto-.15
            auto_left = auto-.15
        if self.state == "charge":
            self.goal = self.hide
            if charge >= full-.08 and not self._beam_threat(obs, enemy):
                self.state, self.reason = "peek", "carry charged beam to firing point"
                self.deadline = now+min(1.8, auto_left-.15)
                self.progress_at, self.progress_position = now, tuple(me["pos"])
            elif auto_left <= .15:
                self._withdraw(obs, "opponent beam denied the peek")
            else:
                return self._control(me, enemy, slot, laser, self._motion(me, self.hide, False), hold=True)
        if self.state == "peek":
            self.goal = self.peek
            time_left = auto_left
            if (charge <= .01 or time_left < self._travel(me, d_peek, True)+.15
                    or self._beam_threat(obs, enemy) or me["energy"] < 30):
                self._withdraw(obs, "peek no longer has a safe charge window", True)
            elif charge >= full and self._can_shoot(me["pos"], me, enemy, laser, actual=True):
                self.state, self.reason = "release", "release aligned clear charged beam"
                self.release_at = now
                self.goal = tuple(me["pos"])
                # Hold movement for the emission boundary. Moving behind the
                # wall before observing charge reset could throw away the beam.
                return self._control(me, enemy, slot, laser, [0., 0.], hold=False)
            else:
                return self._control(me, enemy, slot, laser, self._motion(me, self.peek, True), True, True)
        if self.state == "release":
            self.goal = tuple(me["pos"])
            if charge > 0 and now-self.release_at < .25:
                return self._control(me, enemy, slot, laser, [0., 0.], hold=False)
            self._withdraw(obs, "return behind cover after beam")
            self.progress_at, self.progress_position = now, tuple(me["pos"])
        if self.state == "retreat":
            self.goal = self.hide
            if d_hide <= .8 and math.hypot(*me["vel"][:2]) < 2:
                if self.abort_reason != "return behind cover after beam":
                    reason = self.abort_reason
                    self.next_search = now+1
                    self.clear(reason)
                    return None
                self.state, self.reason = "cooldown", "pay laser cooldown behind cover"
                self.deadline = now+max(3, laser.get("cooldown", 0)+1)
                return self._control(me, enemy, slot, laser, self._motion(me, self.hide, False))
            return self._control(me, enemy, slot, laser, self._motion(me, self.hide, True), me["energy"] > 27)
        return None
