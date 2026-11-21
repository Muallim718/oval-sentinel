"""Screen other gun/laser lanes while finishing one actually weak opponent.

This is a short side/retreat commitment, not a claim of global safety. Mortars
and unseen attackers are not protected by the wall model. The initial exposed
crossing is bounded and charged against a conservative health reserve.
"""
from dataclasses import dataclass
import math
import time

from .combat import Combat
from .cover import CoverPlanner, firing_lane
from .geometry import angle_error, distance, unit
from .movement import forecast


@dataclass(frozen=True)
class SelectivePlan:
    goal: tuple
    target: dict
    move: tuple
    holding: bool
    finish_eta: float
    transition_eta: float
    risk: float


class SelectiveCover:
    MAX_ROUTE = 18.0
    MAX_CROSSING = .65
    MAX_FINISH = 2.0
    MAX_COMMITMENT = 3.5
    MAX_ANCHORS = 12
    SEARCH_SECONDS = .005

    def __init__(self, world, config, shelter=None):
        self.world, self.config = world, config
        self.shelter = shelter or CoverPlanner(world, config)
        self.combat = Combat(world, config)
        self.goal = self.target_id = self.plan = None
        self.state, self.reason = "idle", "no selective finish"
        self.started = self.deadline = -1
        self.screened_once = False
        self.initial_enemies = set()
        self.anchors = self.rays = 0
        self.enemy_armor = 0.
        for upgrade in config.get("upgrades", ()):
            for effect in upgrade.get("effects", ()):
                if effect.get("path") == "mech.armor":
                    self.enemy_armor += effect.get("add", 0)*upgrade.get("max", 1)

    def cancel(self, reason="ordinary protection resumed"):
        self.goal = self.target_id = self.plan = None
        self.state, self.reason = "idle", reason
        self.screened_once = False
        self.initial_enemies = set()

    def _visible(self, point, me, enemy):
        visible, rays = firing_lane(self.world, self.config, point, me, enemy)
        self.rays += rays
        return visible

    def _point(self, xy, me, circle):
        if distance(xy, circle[0])+me["stats"]["radius"]+4 >= circle[1]:
            return None
        p = (*xy[:2], self.world.ground(*xy[:2]))
        return p if self.world.body_clear(*p, me["stats"]["radius"]+.35, me["stats"]["height"],
                                         me["stats"]["step_up"]) else None

    def _weak(self, me, enemy, gun):
        hp = enemy.get("hp", math.inf)
        if not isinstance(hp, (int, float)) or not math.isfinite(hp):
            return False
        damage = gun["stats"]["damage"]*(1-self.enemy_armor)
        shots = math.ceil(hp/max(.001, damage))
        return (0 < hp <= enemy.get("max_hp", 1400)*.25 and
                "mortar" not in enemy.get("weapons", ()) and
                shots <= min(6, gun.get("ammo", 0)) and gun.get("reload", 0) <= 0)

    def _shot(self, me, enemy, gun, point):
        hypothetical = dict(me, pos=list(point))
        solution = self.combat.solve(hypothetical, enemy, gun)
        if solution is None:
            return None
        aim = solution[0]
        if not me["stats"]["min_pitch"] <= aim[1] <= me["stats"]["max_pitch"]:
            return None
        shots = math.ceil(enemy["hp"]/max(.001, gun["stats"]["damage"]*(1-self.enemy_armor)))
        turn = max(abs(angle_error(aim[0], me["aim"][0]))/me["stats"]["turn_rate"],
                   abs(aim[1]-me["aim"][1])/me["stats"]["pitch_rate"])
        return (max(turn, gun.get("cooldown", 0))+(shots-1)*gun["stats"]["cooldown"]+
                distance(point, enemy["pos"])/gun["stats"]["speed"])

    def _path(self, me, goal, circle):
        p, velocity = tuple(me["pos"]), list(me["vel"][:2])
        path = [(0., p)]
        s = me["stats"]
        for step in range(1, 36):
            direction = unit(goal[0]-p[0], goal[1]-p[1])
            dv = [direction[i]*s["walk_speed"]-velocity[i] for i in range(2)]
            f = min(1, s["ground_accel"]*.05/max(1e-9, math.hypot(*dv)))
            velocity = [velocity[i]+dv[i]*f for i in range(2)]
            q = self._point((p[0]+velocity[0]*.05, p[1]+velocity[1]*.05), me, circle)
            if q is None or not self.world.walk_clear(p, q, s["radius"]+.35, s["height"],
                                                      s["step_up"], s["max_slope_deg"]):
                return None
            p = q
            if step % 2 == 0 or distance(p, goal) <= 1.5:
                path.append((step*.05, p))
            if distance(p, goal) <= 1.5:
                return path
        return None

    def _damage(self, me, enemy, seconds, front=False):
        if seconds <= 0:
            return 0.
        kinds = enemy.get("weapons", ["gun"])
        scale = 1+self.config["cubes"]["damage_per_cube"]*min(enemy.get("cubes", 0), self.config["cubes"]["stat_cap"])
        bearing = math.atan2(enemy["pos"][1]-me["pos"][1], enemy["pos"][0]-me["pos"][0])
        rear = not front and abs(angle_error(bearing, me["aim"][0])) > math.pi/2
        multiplier = (me["stats"].get("rear_mult", 1.5) if rear else 1)*(1-me["stats"].get("armor", 0))
        damage = 0.
        if "gun" in kinds:
            gun = self.config["weapons"]["gun"]
            damage += (1+int(seconds/gun["cooldown"]))*gun["damage"]
        if "laser" in kinds:
            laser = self.config["weapons"]["laser"]
            if enemy.get("charging"):
                damage += laser["damage"]
            else:
                fraction = laser["min_frac"]+(1-laser["min_frac"])*min(1, seconds/laser["charge"])
                damage += laser["damage"]*fraction
        if "lightning" in kinds:
            lightning = self.config["weapons"]["lightning"]
            if distance(me["pos"], enemy["pos"]) < lightning["range"]+seconds*self.config["mech"]["boost_speed"]:
                damage += (1+int(seconds/lightning["cooldown"]))*lightning["damage"]
        return damage*scale*multiplier

    def _evaluate(self, obs, goal, target, others, gun, circle, deadline):
        me = obs["self"]
        if any(self._visible(goal, me, e) for e in others):
            return None
        finish = self._shot(me, target, gun, goal)
        if finish is None or finish > self.MAX_FINISH:
            return None
        path = self._path(me, goal, circle)
        if path is None:
            return None
        exposures = {e["id"]: 0. for e in others}
        permanently_screened = False
        transition = 0.
        for t, point in path:
            if time.perf_counter() >= deadline or self._shot(me, target, gun, point) is None:
                return None
            open_ids = [e["id"] for e in others if self._visible(point, me, e)]
            if open_ids:
                if permanently_screened:
                    return None
                transition = t+.1
                for ident in open_ids:
                    exposures[ident] = t+.1
            else:
                permanently_screened = True
        if not permanently_screened or transition > self.MAX_CROSSING:
            return None
        window = max(finish, path[-1][0])+.1
        risk = self._damage(me, target, window, front=True)
        risk += sum(self._damage(me, e, exposures[e["id"]]) for e in others)
        if me["hp"]-risk < max(250, .25*me["max_hp"]):
            return None
        return finish, transition, risk

    def choose(self, obs, threats, circle, *, recovering=False, quiet_shelter=False):
        self.plan = None
        self.anchors = self.rays = 0
        me, now = obs["self"], obs["t"]
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if (not recovering or quiet_shelter or gun is None or me["hp"] < .35*me["max_hp"] or not me["in_zone"]
                or not me["grounded"] or me["energy"] < 25 or obs.get("alive", 16) <= 2
                or abs(me["pos"][2]-self.world.ground(*me["pos"][:2])) > me["stats"]["step_up"]+.5):
            self.cancel("selective finish yields to health, zone, reload or elevation")
            return None
        enemies = {e["id"]: e for e, c in threats if e.get("kind") == "mech" and c >= .25
                   and distance(me["pos"], e["pos"]) < 300}
        enemies.update({e["id"]: e for e in obs.get("mechs", ()) if e.get("kind") == "mech"
                        and distance(me["pos"], e["pos"]) < 300})
        observed = {e["id"]: e for e in obs.get("mechs", ()) if e.get("kind") == "mech"}
        if self.target_id is not None:
            target = observed.get(self.target_id)
            if (target is None or not self._weak(me, target, gun) or now > self.deadline
                    or any(e.get("type") == "kill" and e.get("target") == self.target_id for e in obs.get("events", ()))):
                self.cancel("weak target vanished, recovered, died or exhausted the short window")
                return None
            if not self.screened_once and now-self.started > self.MAX_CROSSING+.1:
                self.cancel("actual side step did not establish its screen in time")
                return None
            if any(e["id"] not in self.initial_enemies and e["id"] != self.target_id
                   and self._visible(me["pos"], me, e) for e in enemies.values()):
                self.cancel("new observed firing lane entered the crossing")
                return None
            if any(e.get("type") == "damaged" and e.get("by") not in (None, self.target_id)
                   and (self.screened_once or e.get("by") not in self.initial_enemies)
                   for e in obs.get("events", ())):
                self.cancel("actual second attacker broke the screened finish")
                return None
            candidates = [target]
        else:
            if sum(self._visible(me["pos"], me, e) for e in enemies.values()) < 2:
                return None
            candidates = sorted((e for e in observed.values() if self._weak(me, e, gun)), key=lambda e: e["hp"])
        if any(p.get("kind") == "mortar" and distance(me["pos"], p["pos"]) < 160 for p in obs.get("projectiles", ())):
            self.cancel("observed mortar trajectory is outside the wall model")
            return None
        deadline = time.perf_counter()+self.SEARCH_SECONDS
        for target in candidates[:2]:
            others = [e for e in enemies.values() if e["id"] != target["id"]]
            if not others or any("mortar" in e.get("weapons", ()) and distance(me["pos"], e["pos"]) < 235 for e in others):
                continue
            current_open = [e for e in others if self._visible(me["pos"], me, e)]
            if self.screened_once and current_open or any(e.get("charging") for e in current_open):
                self.cancel("a flank or charging lane broke actual shelter")
                return None
            anchors = ([self.goal] if self.goal is not None else sorted(
                (xy for xy in self.shelter._anchors(me) if distance(me["pos"], xy) <= self.MAX_ROUTE),
                key=lambda xy: distance(me["pos"], xy)))
            for xy in anchors[:self.MAX_ANCHORS]:
                if time.perf_counter() >= deadline:
                    return None
                self.anchors += 1
                goal = self._point(xy, me, circle)
                # This is not a chase towards the weak enemy. Move sideways or
                # retreat while obtaining a real screen against the other lanes.
                if goal is None or distance(goal, target["pos"]) < distance(me["pos"], target["pos"])-2:
                    continue
                result = self._evaluate(obs, goal, target, others, gun, circle, deadline)
                if result is None:
                    continue
                if self.target_id is None:
                    self.started, self.deadline = now, now+self.MAX_COMMITMENT
                    self.initial_enemies = set(enemies)
                self.goal, self.target_id = goal, target["id"]
                self.screened_once |= not current_open
                delta = (goal[0]-me["pos"][0], goal[1]-me["pos"][1])
                speed = me["stats"]["walk_speed"]
                command = tuple((delta[i]*3-.15*me["vel"][i])/speed for i in range(2))
                n = max(1, math.hypot(*command))
                command = tuple(v/n for v in command)
                q = forecast(me, command, speed, .25)
                if (not self.world.walk_clear(me["pos"], q, me["stats"]["radius"]+.35,
                                              me["stats"]["height"], me["stats"]["step_up"], me["stats"]["max_slope_deg"])
                        or self.screened_once and any(self._visible(q, me, e) for e in others)):
                    self.cancel("next controlled step would lose the screen")
                    return None
                holding = distance(me["pos"], goal) < 1.5 and math.hypot(*me["vel"][:2]) < 2
                if holding:
                    command = (0., 0.)
                self.state = "hold" if holding else "side step"
                self.reason = "keep one short weak-target shot while other known lanes are blocked"
                self.plan = SelectivePlan(goal, target, command, holding, *result)
                return self.plan
        if self.target_id is not None:
            self.cancel("live selective route or shot is no longer viable")
        return None
