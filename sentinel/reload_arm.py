"""Collect nearby equipment on a short route while preserving gun control.

Choose a reload break, a covered approach, or a bounded early duel detour.
Arrival and actual initial equip time both enter the damage budget.
"""
from dataclasses import dataclass
import math
import time

from .cover import firing_lane
from .geometry import angle_error, distance, unit


@dataclass(frozen=True)
class ArmMission:
    goal: tuple
    waypoint: tuple
    kind: str
    pickup_id: int
    take: int | None
    eta: float
    ready_at: float
    protected: bool
    sprint: bool = False
    move: tuple | None = None


class ReloadArm:
    START_UNTIL = 90.0
    DUEL_UNTIL = 150.0
    MAX_SECONDS = 3.0
    SEARCH_SECONDS = .004
    MAX_CANDIDATES = 6

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.current = None
        self.plan = None
        self.state, self.reason = "idle", "no short equipment opportunity"
        self.pickups = {}
        self.rejected = {}
        self.last_observation = None
        self.previous_kind = None
        self.ready_at = -1
        self.initial_equip = False

    def cancel(self, reason="ordinary control resumed", now=None, reject=False):
        if reject and self.current and now is not None:
            self.rejected[self.current["id"]] = now+5
        self.current, self.plan = None, None
        self.state, self.reason = "idle", reason

    def update(self, obs):
        key = (obs.get("tick"), obs["t"])
        if key == self.last_observation:
            return
        self.last_observation = key
        now, me = obs["t"], obs["self"]
        self.rejected = {i: t for i, t in self.rejected.items() if t > now}
        visible = {p["id"]: p for p in obs.get("pickups", ())}
        for ident, (seen, pickup) in list(self.pickups.items()):
            near = distance(me["pos"], pickup["pos"]) < 7 and abs(me["pos"][2]-pickup["pos"][2]) < 4
            eye = (*me["pos"][:2], me["pos"][2]+me["stats"]["eye_height"])
            if now-seen > self.MAX_SECONDS or (near and ident not in visible and self.world.line_clear(
                    eye, (*pickup["pos"][:2], pickup["pos"][2]+1))):
                self.pickups.pop(ident, None)
        for ident, pickup in visible.items():
            self.pickups[ident] = (now, dict(pickup))
        for event in obs.get("events", ()):
            if event["type"] == "take_failed" and event.get("reason") in ("gone", "have", "full"):
                self.pickups.pop(event["id"], None)
                self.rejected[event["id"]] = now+5
        if len(self.pickups) > 16:
            self.pickups = dict(sorted(self.pickups.items(), key=lambda item: item[1][0], reverse=True)[:16])
        second = me["weapons"][1]
        kind = second["kind"] if second else None
        if kind is not None and kind != self.previous_kind:
            self.current = self.plan = None
            self.ready_at = now+max(0, second.get("cooldown", 0))
            self.initial_equip = second.get("cooldown", 0) > .001
        if self.initial_equip and second is not None and second.get("cooldown", 0) <= .001:
            self.initial_equip = False
        self.previous_kind = kind
        if kind is not None:
            self.state = "equipping" if self.initial_equip else "armed"
            self.reason = "actual secondary received; ordinary combat retains control"

    def _point(self, xy, me, circle):
        if distance(xy, circle[0]) > circle[1]-me["stats"]["radius"]-3:
            return None
        p = (*xy[:2], self.world.ground(*xy[:2]))
        return p if self.world.body_clear(*p, me["stats"]["radius"]+.3, me["stats"]["height"],
                                         me["stats"]["step_up"]) else None

    def _travel(self, me, pickup, circle):
        goal = self._point(pickup["pos"], me, circle)
        s = me["stats"]
        if goal is None or abs(pickup["pos"][2]-goal[2]) >= 4:
            return None
        if not self.world.walk_clear(me["pos"], goal, s["radius"]+.3, s["height"],
                                     s["step_up"], s.get("max_slope_deg", 50)):
            return None
        p, velocity = tuple(me["pos"]), list(me["vel"][:2])
        path = [p]
        band = self.config["loot"]["pickup_radius"]-.35
        for tick in range(61):
            if distance(p, goal) <= band:
                return tick*.05, path, goal
            if tick == 60:
                break
            direction = unit(goal[0]-p[0], goal[1]-p[1])
            dv = [direction[i]*s["walk_speed"]-velocity[i] for i in range(2)]
            fraction = min(1, s["ground_accel"]*.05/max(1e-9, math.hypot(*dv)))
            velocity = [velocity[i]+dv[i]*fraction for i in range(2)]
            xy = (p[0]+velocity[0]*.05, p[1]+velocity[1]*.05)
            q = self._point(xy, me, circle)
            if q is None or not self.world.walk_clear(p, q, s["radius"]+.3, s["height"],
                                                       s["step_up"], s.get("max_slope_deg", 50)):
                return None
            path.append(q)
            p = q
        return None

    def _incoming(self, obs, path, window, deadline):
        me, damage = obs["self"], 0.
        for p in sorted(obs.get("projectiles", ()), key=lambda p: distance(me["pos"], p["pos"]))[:16]:
            mortar = p["kind"] == "mortar"
            for i in range(1, max(2, math.ceil(window/.05)+1)):
                if time.perf_counter() >= deadline:
                    return math.inf
                a, b = (i-1)*.05, i*.05
                own_a, own_b = path[min(i-1, len(path)-1)], path[min(i, len(path)-1)]
                bullet_a = [p["pos"][j]+p["vel"][j]*a for j in range(3)]
                bullet_b = [p["pos"][j]+p["vel"][j]*b for j in range(3)]
                if mortar:
                    gravity = self.config["weapons"]["mortar"]["gravity"]
                    bullet_a[2] -= gravity*a*a/2
                    bullet_b[2] -= gravity*b*b/2
                r = [bullet_a[j]-own_a[j] for j in range(2)]
                v = [bullet_b[j]-bullet_a[j]-(own_b[j]-own_a[j]) for j in range(2)]
                t = max(0, min(1, -sum(r[j]*v[j] for j in range(2))/max(1e-9, sum(x*x for x in v))))
                d = math.hypot(*(r[j]+v[j]*t for j in range(2)))
                z = bullet_a[2]+(bullet_b[2]-bullet_a[2])*t
                radius = me["stats"]["radius"]+(7 if mortar else .6)
                if d <= radius and own_a[2]-(7 if mortar else 0) <= z <= own_a[2]+me["stats"]["height"]+1:
                    contact = tuple(bullet_a[j]+(bullet_b[j]-bullet_a[j])*t for j in range(3))
                    if self.world.line_clear(p["pos"], contact):
                        damage += 360 if mortar else self.config["npc"]["damage"] if p["kind"] == "npc" else 45
                        break
        return damage

    @staticmethod
    def _quick_duel_route(me, pickup, eta, goal, enemies, risk):
        if pickup["kind"] not in ("laser", "lightning") or eta > 1.25 or len(enemies) != 1:
            return False
        enemy = next(iter(enemies.values()))
        current_distance = distance(me["pos"], enemy["pos"])
        return (enemy.get("weapons") == ["gun"] and enemy.get("hp", 1400) > 240 and
                current_distance >= 52 and distance(goal, enemy["pos"]) >= current_distance-2.5 and
                risk <= me["hp"]*.27)

    def _admit(self, obs, pickup, threats, circle, reload_window, deadline,
               continuing=False, duel_route=False, duel_only=False):
        me = obs["self"]
        travel = self._travel(me, pickup, circle)
        if travel is None:
            return None
        eta, path, goal = travel
        equip = max(self.config["loot"]["equip_s"], self.config["weapons"][pickup["kind"]]["cooldown"])
        window = eta+equip
        samples = [(eta*i/3, path[round((len(path)-1)*i/3)]) for i in range(4)]
        samples.append((window, path[-1]))
        exposed, risk = set(), 0.
        enemies = {e["id"]: e for e, c in threats if e.get("kind") == "mech" and c >= .25}
        enemies.update({e["id"]: e for e in obs.get("mechs", ()) if e.get("kind") == "mech"})
        for enemy in enemies.values():
            if time.perf_counter() >= deadline:
                return None
            visible = False
            for t, point in samples:
                predicted = dict(enemy)
                predicted["pos"] = [enemy["pos"][j]+enemy.get("vel", [0, 0, 0])[j]*min(1, t) for j in range(3)]
                if firing_lane(self.world, self.config, point, me, predicted)[0]:
                    visible = True
                    break
            if not visible:
                # Do not extend a hiding route into a hunter that can physically
                # reach the destination before the secondary finishes equipping.
                if distance(enemy["pos"], goal)/self.config["mech"]["boost_speed"] < window+.4:
                    return None
                continue
            exposed.add(enemy["id"])
            if len(exposed) > 1 or enemy.get("charging"):
                return None
            kinds = enemy.get("weapons", ["gun"])
            d = min(distance(me["pos"], enemy["pos"]), distance(goal, enemy["pos"]))
            if d-self.config["mech"]["boost_speed"]*window < 14:
                return None
            factor = 1+self.config["cubes"]["damage_per_cube"]*min(enemy.get("cubes", 0), self.config["cubes"]["stat_cap"])
            multiplier = 1.5 if abs(angle_error(math.atan2(enemy["pos"][1]-me["pos"][1],
                                                        enemy["pos"][0]-me["pos"][0]), me["aim"][0])) > math.pi/2 else 1
            if "gun" in kinds:
                gun = self.config["weapons"]["gun"]
                risk += max(0, window-d/gun["speed"])*gun["damage"]/gun["cooldown"]*factor*multiplier
            if "laser" in kinds and d < self.config["weapons"]["laser"]["range"]:
                laser = self.config["weapons"]["laser"]
                risk += (1+int(window/(laser["charge"]+laser["cooldown"])))*laser["damage"]*factor
            if "mortar" in kinds and d < 235:
                risk += 360*factor
            if "lightning" in kinds and d-self.config["mech"]["boost_speed"]*window < self.config["weapons"]["lightning"]["range"]:
                return None
        protected = not exposed
        needs_duel_route = not continuing and (duel_only or
                           (not protected and (reload_window <= 0 or eta > reload_window+.1)))
        if needs_duel_route and not duel_route:
            return None
        for npc in (e for e in obs.get("mechs", ()) if e.get("kind") == "npc"):
            if any(distance(point, npc["pos"]) < 90 and self.world.line_clear(
                    (*npc["pos"][:2], npc["pos"][2]+3), (*point[:2], point[2]+me["stats"]["height"]*.5))
                   for _, point in samples):
                risk += window*self.config["npc"]["damage"]
        risk += self._incoming(obs, path, window, deadline)
        risk *= 1-me["stats"].get("armor", 0)
        if me["hp"]-risk < max(180, me["max_hp"]*.20):
            return None
        if needs_duel_route and not self._quick_duel_route(me, pickup, eta, goal, enemies, risk):
            return None
        return eta, goal, protected, equip, needs_duel_route

    def choose(self, obs, threats, circle, recovering=False):
        self.update(obs)
        now, me = obs["t"], obs["self"]
        self.plan = None
        if me["weapons"][1] is not None:
            return None  # Receipt immediately ends route ownership, not a wait mode.
        if (not me["grounded"] or not me["in_zone"] or me["hp"] < me["max_hp"]*.30
                or obs.get("alive", 16) <= 2 or me["energy"] < 25
                or me["pos"][2] > self.world.ground(*me["pos"][:2])+1.5):
            self.cancel("equipment detour yields to immediate survival")
            return None
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if gun is None:
            self.cancel("no arm gun reload opportunity")
            return None
        reload_window = gun.get("reload", 0) or (gun["stats"]["reload"] if gun.get("ammo", 0) == 0 else 0)
        duel_route = (now <= self.DUEL_UNTIL and obs.get("alive", 16) >= 9 and not recovering and
                      me["hp"] >= me["max_hp"]*.78)
        deadline = time.perf_counter()+self.SEARCH_SECONDS
        if self.current:
            if (now > self.current["until"] or self.current["id"] not in self.pickups or
                    (self.current.get("duel_route") and me["hp"] < me["max_hp"]*.65)):
                self.cancel("short equipment commitment expired or became unsafe", now, True)
                return None
            pickup = self.pickups[self.current["id"]][1]
            approved = self._admit(obs, pickup, threats, circle, reload_window, deadline, continuing=True)
            if approved is None:
                self.cancel("equipment corridor or damage budget changed", now, True)
                return None
        else:
            if now > self.START_UNTIL and not duel_route:
                return None
            candidates = sorted((p for p in obs.get("pickups", ()) if p["kind"] in ("laser", "lightning", "mortar")
                                 and p["id"] not in self.rejected),
                                key=lambda p: (-{"laser": 3, "lightning": 3, "mortar": 1}[p["kind"]], distance(me["pos"], p["pos"])))
            approved = pickup = None
            for pickup in candidates[:self.MAX_CANDIDATES]:
                if time.perf_counter() >= deadline:
                    break
                approved = self._admit(obs, pickup, threats, circle, reload_window, deadline,
                                       duel_route=duel_route, duel_only=now > self.START_UNTIL)
                if approved:
                    break
            if approved is None:
                self.reason = "no viable short reload or covered pickup"
                return None
            eta, _, protected, _, dash = approved
            if dash:
                until = now+min(1.6, max(.65, eta*1.2+.25))
            else:
                until = now+self.MAX_SECONDS if protected else now+min(self.MAX_SECONDS, reload_window+.25)
            self.current = {"id": pickup["id"], "until": until, "position": tuple(me["pos"]),
                            "progress_at": now, "duel_route": dash}
        eta, goal, protected, equip, _ = approved
        if distance(me["pos"], self.current["position"]) >= 1:
            self.current["position"], self.current["progress_at"] = tuple(me["pos"]), now
        elif eta > 0 and now-self.current["progress_at"] > 1:
            self.cancel("equipment approach made no physical progress", now, True)
            return None
        take = pickup["id"] if eta == 0 and abs(me["pos"][2]-pickup["pos"][2]) <= 4 else None
        self.state = "take" if take is not None else "approach"
        self.reason = ("short equipment detour while firing" if self.current["duel_route"] else
                       "short covered pickup" if protected else "collect equipment during arm-gun reload")
        self.ready_at = now+eta+equip
        self.plan = ArmMission(goal, goal, pickup["kind"], pickup["id"], take, eta,
                               self.ready_at, protected, move=(0., 0.) if take is not None else None)
        return self.plan
