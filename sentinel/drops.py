"""Announced supply drops are timed repair missions, not attractive waypoints.

Start a verified ground route early enough to arrive at landing, stay alone in
the capture ring, and yield immediately when the storm or a contest defeats it.
This begins no earlier than the first actual announcement (normally70seconds).
"""
from dataclasses import dataclass
import copy
import math
import time

from .cover import firing_lane
from .geometry import distance, unit
from .navigation import Navigator


@dataclass(frozen=True)
class DropMission:
    goal: tuple
    waypoint: tuple
    sprint: bool
    holding: bool
    eta: float
    capture_at: float
    move: tuple | None = None
    gun_only: bool = True


def future_zone(zone, now, seconds):
    start = max(now, zone["shrink_start"])
    fraction = min(1, max(0, now+seconds-start)/max(.001, zone["shrink_end"]-start))
    return ([zone["center"][i]+fraction*(zone["next_center"][i]-zone["center"][i]) for i in range(2)],
            zone["radius"]+fraction*(zone["next_radius"]-zone["radius"]))


class TimedDrop:
    MAX_ROUTE = 380.0
    MAX_PLAN_SECONDS = .004
    RESERVE_ENERGY = 35.0
    START_LATE_SECONDS = 8.0
    MAX_CAPTURE_LATE = 16.0

    def __init__(self, world, config, navigator=None):
        self.world, self.config = world, config
        # Search state is independent. Sharing the immutable grid and lazy
        # geometry cache avoids rebuilding the whole map for an optional goal.
        self.nav = copy.copy(navigator) if navigator is not None else Navigator(world, config["mech"])
        self.nav.path, self.nav.search, self.nav.goal = [], None, None
        self.nav.search_done, self.nav.next_plan = True, -1
        self.drop_id = None
        self.goal = None
        self.plan = None
        self.state, self.reason = "idle", "no announced repair objective"
        self.landings, self.rejected = {}, {}
        self.last_observation = None
        self.progress_position, self.progress_at = None, -1
        self.eta = self.capture_at = math.inf
        self.capture_progress, self.capture_progress_at = None, -1
        self.cached_route, self.route_key = None, None
        self.search_key, self.next_search = None, -1
        self.now = 0
        self.enemy_speed = config["mech"]["boost_speed"]
        for upgrade in config.get("upgrades", ()):
            for effect in upgrade.get("effects", ()):
                if effect.get("path") == "mech.boost_speed":
                    self.enemy_speed *= effect.get("mul", 1)**upgrade.get("max", 1)

    def cancel(self, reason="drop mission yielded", now=None, reject=False):
        if reject and self.drop_id is not None and now is not None:
            self.rejected[self.drop_id] = now+4
        self.drop_id = self.goal = self.plan = None
        self.state, self.reason = "idle", reason
        self.progress_position = None
        self.capture_progress = None
        self.cached_route, self.route_key = None, None
        self.search_key = None

    def update(self, obs):
        marker = (obs.get("tick"), obs["t"])
        if marker == self.last_observation:
            return
        self.last_observation = marker
        now = obs["t"]
        self.rejected = {i: t for i, t in self.rejected.items() if t > now}
        for drop in obs.get("drops", ()):
            self.landings.setdefault(drop["id"], now+max(0, drop["lands_in"]))
        live = {d["id"] for d in obs.get("drops", ())}
        for event in obs.get("events", ()):
            if event["type"] == "drop" and event["id"] == self.drop_id:
                self.cancel("capture confirmed by server")
        if self.drop_id is not None and self.drop_id not in live:
            self.cancel("announced drop is no longer available")

    def _point(self, xy, me, circle, growth=False):
        if distance(xy, circle[0]) > circle[1]-me["stats"]["radius"]-3:
            return None
        p = (*xy[:2], self.world.ground(*xy[:2]))
        scale = (1+self.config["cubes"]["size_per_cube"]*(me.get("cubes", 0)+self.config["drops"]["cubes"]))/(
            1+self.config["cubes"]["size_per_cube"]*me.get("cubes", 0)) if growth else 1
        return p if self.world.body_clear(*p, me["stats"]["radius"]*scale+.35,
                                         me["stats"]["height"]*scale, me["stats"]["step_up"]) else None

    def _walk(self, a, b, me):
        s = me["stats"]
        return self.world.walk_clear(a, b, s["radius"]+.35, s["height"],
                                     s["step_up"], s.get("max_slope_deg", 50))

    def _route(self, me, goal, circle, threats):
        if self._walk(me["pos"], goal, me):
            return [tuple(me["pos"]), goal]
        key = (goal[0], goal[1], me["stats"]["radius"], me["stats"]["height"])
        if self.cached_route and self.route_key == key:
            closest = min(range(len(self.cached_route)), key=lambda i: distance(me["pos"], self.cached_route[i]))
            if distance(me["pos"], self.cached_route[closest]) < 6 and closest+1 < len(self.cached_route):
                closest += 1
            tail = self.cached_route[closest:]
            if tail and self._walk(me["pos"], tail[0], me) and self._walk(tail[-1], goal, me):
                return [tuple(me["pos"]), *tail]
            self.cached_route = None
        if self.search_key != key:
            self.nav.search = None
            self.search_key, self.next_search = key, self.now
        if self.now < self.next_search:
            return None
        self.next_search = self.now+.3
        route = self.nav.plan(me["pos"], goal, circle, [e["pos"] for e, _ in threats[:4]])
        if not self.nav.search_done or not route:
            return None
        # An exhausted A* can return partial progress. Both actual end legs must
        # be physically reachable; a nearby grid cell across a wall is not a path.
        if (distance(route[-1], goal) > 9 or not self._walk(route[-1], goal, me)
                or not self._walk(me["pos"], route[0], me)):
            return None
        self.cached_route = [tuple(me["pos"]), *route, goal]
        self.route_key = key
        return self.cached_route

    def _schedule(self, me, route, sprint):
        # A conservative path-length ETA with acceleration plus braking. Sprint
        # is optional and only budgeted until the stated energy reserve.
        length = sum(distance(a, b) for a, b in zip(route, route[1:]))
        s = me["stats"]
        fast = min(length, max(0, me["energy"]-self.RESERVE_ENERGY)/s["boost_drain"]*s["boost_speed"]) if sprint else 0
        eta = fast/s["boost_speed"]+(length-fast)/s["walk_speed"]+.25
        return length, eta

    def _sample(self, route, fraction):
        lengths = [distance(a, b) for a, b in zip(route, route[1:])]
        left = fraction*sum(lengths)
        for i, length in enumerate(lengths):
            if left <= length:
                t = left/max(1e-9, length)
                return tuple(route[i][j]+(route[i+1][j]-route[i][j])*t for j in range(3))
            left -= length
        return route[-1]

    def _risk(self, obs, route, threats, eta, wait, capture_left):
        me = obs["self"]
        horizon = min(6, eta+wait+capture_left)
        if horizon <= 0:
            return 0
        total = 0.0
        considered = sorted((ec for ec in threats if ec[0].get("kind") == "mech" and ec[1] >= .3),
                            key=lambda ec: distance(me["pos"], ec[0]["pos"]))
        # More than four nearby lanes is a battle, not a four-second repair stop.
        if sum(distance(me["pos"], e["pos"]) < 180 for e, _ in considered) > 4:
            return math.inf
        for enemy, confidence in considered[:4]:
            damage = 0
            laser_window = 0
            kinds = enemy.get("weapons", ["gun"])
            scale = 1+self.config["cubes"]["damage_per_cube"]*min(
                enemy.get("cubes", 0), self.config["cubes"]["stat_cap"])
            # Four intervals bound route sampling. Once a hunter has had a
            # second to reposition, assume it can establish a firing lane.
            for k in range(4):
                t = horizon*(k+.5)/4
                p = self._sample(route, min(1, t/max(.01, eta)))
                exposed = firing_lane(self.world, self.config, p, me, enemy)[0]
                if not exposed and t <= 1:
                    continue
                d = max(0, distance(p, enemy["pos"])-self.enemy_speed*t)
                dt = horizon/4
                if "gun" in kinds and d <= self.config["weapons"]["gun"]["range"]:
                    stats = self.config["weapons"]["gun"]
                    damage += dt*stats["damage"]/stats["cooldown"]
                if "lightning" in kinds and d <= self.config["weapons"]["lightning"]["range"]:
                    stats = self.config["weapons"]["lightning"]
                    damage += dt*stats["damage"]/stats["cooldown"]
                if "laser" in kinds and d <= self.config["weapons"]["laser"]["range"]:
                    laser_window += dt
                if "mortar" in kinds and d <= 235:
                    stats = self.config["weapons"]["mortar"]
                    damage += dt*(stats["damage"]+stats["splash"])/max(1, stats["cooldown"])
            if laser_window > 0:
                stats = self.config["weapons"]["laser"]
                first = 0 if enemy.get("charging") else stats["charge"]
                if laser_window >= first:
                    shots = 1+int((laser_window-first)/(stats["charge"]+stats["cooldown"]))
                    cookoff = 1+stats.get("cookoff", .6) if any(
                        w and w["kind"] == "mortar" for w in me["weapons"]) else 1
                    damage += shots*stats["damage"]*cookoff
            total += damage*scale*(1-me["stats"].get("armor", 0))
        for npc in (e for e in obs.get("mechs", ()) if e.get("kind") == "npc"):
            if distance(me["pos"], npc["pos"]) <= 90:
                total += horizon*self.config["npc"]["damage"]
        # Existing fast rounds are a separate immediate cost. Closest approach
        # is continuous, so a252m/s bullet cannot skip between sparse samples.
        for p in sorted(obs.get("projectiles", ()), key=lambda p: distance(me["pos"], p["pos"]))[:16]:
            rx, ry = p["pos"][0]-me["pos"][0], p["pos"][1]-me["pos"][1]
            vx, vy = p["vel"][0]-me["vel"][0], p["vel"][1]-me["vel"][1]
            t = max(0, min(1, -(rx*vx+ry*vy)/max(1, vx*vx+vy*vy)))
            radius = me["stats"]["radius"]+(8 if p["kind"] == "mortar" else 1)
            z = p["pos"][2]+p["vel"][2]*t
            if p["kind"] == "mortar":
                z -= self.config["weapons"]["mortar"]["gravity"]*t*t/2
            if (math.hypot(rx+vx*t, ry+vy*t) < radius and
                    me["pos"][2]-3 < z < me["pos"][2]+me["stats"]["height"]+3):
                total += 360 if p["kind"] == "mortar" else 45
        return total

    def choose(self, obs, threats, circle, recovering=False):
        self.update(obs)
        now, me = obs["t"], obs["self"]
        self.now = now
        self.plan = None
        first_call = min(self.config["drops"]["times"])
        if (now < first_call or obs.get("alive", 16) <= 2 or not me["in_zone"] or not me["grounded"]
                or me["pos"][2] > self.world.ground(*me["pos"][:2])+1.5):
            self.cancel("repair mission yields to phase, final duel, storm or elevation")
            return None
        drops = [d for d in obs.get("drops", ()) if d["id"] not in self.rejected
                 and d.get("holder") in (None, me["id"])
                 and (now <= self.landings[d["id"]]+self.START_LATE_SECONDS or
                      d["id"] == self.drop_id and self.state in ("approach", "landing", "capture"))]
        if not drops:
            self.cancel("no available timely uncontested drop")
            return None
        drops.sort(key=lambda d: (d["id"] != self.drop_id, distance(me["pos"], d["pos"])))
        drop = drops[0]
        if (distance(me["pos"], drop["pos"]) > drop.get("radius", self.config["drops"]["radius"])-1
                and any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])):
            self.cancel("finish held laser before committing timed ground movement")
            return None
        self.drop_id = drop["id"]
        land_at = self.landings[self.drop_id]
        radius = drop.get("radius", self.config["drops"]["radius"])
        if abs(drop["pos"][2]-self.world.ground(*drop["pos"][:2])) >= 4:
            self.cancel("drop is not a ground objective", now, True)
            return None
        self.nav.set_body(me["stats"])
        deadline = time.perf_counter()+self.MAX_PLAN_SECONDS
        points = [tuple(drop["pos"][:2])]
        ring = min(3, max(0, radius-me["stats"]["radius"]-1))
        points += [(drop["pos"][0]+math.cos(i*math.tau/8)*ring,
                    drop["pos"][1]+math.sin(i*math.tau/8)*ring) for i in range(8)]
        if self.goal is not None and distance(self.goal, drop["pos"]) <= ring+.1:
            points.insert(0, self.goal[:2])
        goal = route = None
        for xy in points:
            if time.perf_counter() >= deadline:
                break
            goal = self._point(xy, me, circle, growth=True)
            if goal is not None:
                route = self._route(me, goal, circle, threats)
                if route is not None:
                    break
                if not self.nav.search_done:
                    break
        if goal is None or route is None:
            self.state, self.reason = "planning", "waiting for complete body-valid ground route"
            return None
        length, walking_eta = self._schedule(me, route, False)
        if length > self.MAX_ROUTE:
            self.cancel("drop route exceeds bounded repair detour", now, True)
            return None
        # Spend energy only when the walking route would arrive late. The drop
        # itself refills energy, but an abandoned plan still needs an escape.
        sprint = walking_eta > max(0, land_at-now)+.5 and me["energy"] > self.RESERVE_ENERGY+10
        _, eta = self._schedule(me, route, sprint)
        inside = distance(me["pos"], drop["pos"]) <= radius-1
        progress = drop.get("progress", 0) if inside and drop.get("holder") == me["id"] else 0
        capture_left = max(0, drop.get("capture_s", self.config["drops"]["capture_s"])-progress)
        eta = 0 if inside else eta
        wait = max(0, land_at-now-eta)
        capture_at = now+eta+wait+capture_left
        end_circle = future_zone(obs["zone"], now, capture_at-now+.5)
        walked, route_length = 0., max(.01, length)
        safe_route = self._point(goal, me, end_circle) is not None
        for i, point in enumerate(route):
            if i:
                walked += distance(route[i-1], point)
            phase = future_zone(obs["zone"], now, eta*walked/route_length+.5)
            if self._point(point, me, phase) is None:
                safe_route = False
                break
        if capture_at > land_at+self.MAX_CAPTURE_LATE or not safe_route:
            self.cancel("capture route or completion loses safe zone", now, True)
            return None
        # A point can be a useful early staging route without a25-second claim
        # that nobody will approach. The final window requires winning the race.
        remaining = capture_at-now
        for enemy, confidence in threats:
            if enemy.get("kind") != "mech" or confidence < .3:
                continue
            d = distance(enemy["pos"], drop["pos"])
            contest_eta = max(0, d-radius)/self.enemy_speed
            if d <= radius+.5 or (max(eta, land_at-now) <= 6 and contest_eta <= remaining+.75):
                self.cancel("hostile can contest before repair completes", now, True)
                return None
        risk = self._risk(obs, route, threats, eta, wait, capture_left)
        if me["hp"]-risk < max(120, me["max_hp"]*.12):
            self.cancel("cannot survive route and capture exposure", now, True)
            return None
        if (not inside and now < land_at-walking_eta-.8) or (inside and wait > 1):
            self.state, self.reason = "scheduled", "wait to depart without camping an open drop"
            self.goal, self.eta, self.capture_at = goal, eta, capture_at
            return None
        if self.progress_position is None or distance(me["pos"], self.progress_position) >= 2:
            self.progress_position, self.progress_at = tuple(me["pos"]), now
        elif not inside and now-self.progress_at > 3:
            self.cancel("repair route made no physical progress", now, True)
            return None
        self.goal, self.eta, self.capture_at = goal, eta, capture_at
        holding = inside and drop["lands_in"] <= 0
        if holding:
            if self.capture_progress is None or progress > self.capture_progress+.02:
                self.capture_progress, self.capture_progress_at = progress, now
            elif now-self.capture_progress_at > .8:
                self.cancel("server capture clock is not advancing", now, True)
                return None
            self.state, self.reason = "capture", "remain alone in actual capture ring"
        elif inside:
            self.state, self.reason = "landing", "announced drop is about to land"
        else:
            self.capture_progress = None
            self.state, self.reason = "approach", "arrive for timed repair capture"
        waypoint = next((p for p in route[1:] if distance(me["pos"], p) > 3), goal)
        move = (0., 0.) if inside else None
        self.plan = DropMission(goal, waypoint, bool(sprint and not inside), holding, eta, capture_at, move,
                                gun_only=not inside)
        return self.plan
