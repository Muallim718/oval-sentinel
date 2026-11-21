"""The decision loop, in priority order: survive zone, escape, recover, loot, fight.

No private seeds, engine internals, or knowledge of unseen objects are used.
"""
import math
import os
import random
from pathlib import Path
from . import tuning
from .combat import Combat, aim_at
from .geometry import World, distance, unit
from .navigation import Navigator
from .memory import LootMemory
from .cover import CoverPlanner
from .movement import GroundSteering
from .altitude import RoofSanctuary


def future_circle(zone, now, seconds):
    """Interpolate FROM the already-current circle, not the phase's old circle."""
    remaining = zone["shrink_end"] - max(now, zone["shrink_start"])
    shrinking = max(0, now+seconds-max(now, zone["shrink_start"]))
    fraction = min(1.0, shrinking/max(0.001, remaining))
    center = [zone["center"][i]+fraction*(zone["next_center"][i]-zone["center"][i]) for i in range(2)]
    radius = zone["radius"]+fraction*(zone["next_radius"]-zone["radius"])
    return center, max(0, radius)


def clamp_circle(point, center, radius):
    dx, dy = point[0]-center[0], point[1]-center[1]
    d = math.hypot(dx, dy)
    if d > radius:
        return (center[0]+dx*radius/max(1e-9, d), center[1]+dy*radius/max(1e-9, d))
    return tuple(point[:2])


class Bot:
    name = "Oval Sentinel"

    def __init__(self, hello):
        self.config = hello["config"]
        self.rng = random.Random(hello.get("seed", 0))
        self.phase = self.rng.random()*math.tau
        self.world = World(Path(hello["map"]["dir"]))
        self.nav = Navigator(self.world, self.config["mech"])
        self.combat = Combat(self.world, self.config)
        self.cover = CoverPlanner(self.world, self.config)
        self.motion = GroundSteering(self.world, self.config)
        self.altitude = RoofSanctuary(self.world, self.config)
        self.cover_active = False
        self.cover_watch_goal = None
        self.cover_watch_position = None
        self.cover_watch_at = -1
        self.seen = {}
        self.goal, self.goal_kind = None, "rotate"
        self.next_goal = -1
        self.last_damage = -100
        self.last_weapon_damage = -100
        self.last_attack = -100
        self.last_position = None
        self.stuck_since = None
        self.jet_until = -1
        self.jet_started_z = 0
        self.sprinting = False
        self.debug = os.environ.get("BOT_DEBUG", "0") == "1"
        self.loot = LootMemory()
        self.objective = None
        self.recovering = False
        self.mode = "loot"
        self.duel = None
        self.fight_range = 65.0

    def remember(self, obs):
        now = obs["t"]
        self.loot.update(obs, self.world)
        for enemy in obs["mechs"]:
            if enemy["kind"] == "mech":
                self.seen[enemy["id"]] = (now, enemy)
        for event in obs["events"]:
            if event["type"] == "damaged":
                self.last_damage = now
                if event.get("weapon") not in (None, "zone"):
                    self.last_weapon_damage = now
            elif event["type"] == "kill":
                self.seen.pop(event["target"], None)
        self.seen = {k:v for k,v in self.seen.items() if now-v[0] < tuning.THREAT_MEMORY}

    def threats(self, now):
        return [(enemy, max(0.25, 1-(now-last)/tuning.THREAT_MEMORY))
                for last, enemy in self.seen.values()]

    @staticmethod
    def weapon_value(kind):
        return {"laser": 3.0, "lightning": 3.0, "mortar": 1.0, "gun": 0.0}.get(kind, 0)

    def select_mode(self, obs):
        """Fight isolated pursuers; recover with hysteresis; avoid crossfire."""
        me = obs["self"]
        ratio = me["hp"]/me["max_hp"]
        if ratio < tuning.RETREAT_HP:
            self.recovering = True
        elif ratio >= 0.90:
            self.recovering = False
        eye = [me["pos"][0], me["pos"][1], me["pos"][2]+me["stats"]["eye_height"]]
        nearby = sorted((e for e in obs["mechs"] if e["kind"] == "mech" and
                         distance(me["pos"],e["pos"]) < 155),
                        key=lambda e: distance(me["pos"],e["pos"]))
        exposed = []
        for e in nearby[:8]:
            ep = e["pos"]
            if self.world.line_clear(eye,[ep[0],ep[1],ep[2]+4.5]):
                exposed.append(e)
        self.duel = None
        self.mode = "recover" if self.recovering else "loot"
        if len(exposed) >= 2:
            self.mode = "recover" if self.recovering else "evade"
        elif exposed:
            enemy = exposed[0]
            finish = enemy.get("hp",1400) < 170
            favorable = (ratio > 0.70 and enemy.get("hp",1400) < me["hp"]*1.12)
            if (favorable and not self.recovering) or finish:
                self.mode, self.duel = "fight", enemy
                second = next((w for w in me["weapons"] if w and w["kind"] != "gun"),None)
                self.fight_range = 65
                if second and second["kind"] == "lightning":
                    self.fight_range = second["stats"]["range"]*0.78
                elif second and second["kind"] == "laser":
                    self.fight_range = 110 if "mortar" in enemy.get("weapons",[]) else 90
                elif "lightning" in enemy.get("weapons",[]):
                    self.fight_range = 85
            else:
                self.mode = "recover" if self.recovering else "evade"

    def goal_score(self, pos, me, circle, threats, kind="hide", value=0):
        """Lower is better. Covered positions are safer than equally distant open ones."""
        p = (pos[0], pos[1], self.world.ground(*pos[:2]))
        if not self.world.body_clear(*p, me["stats"]["radius"]+0.4, me["stats"]["height"]):
            return math.inf
        travel = distance(me["pos"], p)
        outside = max(0, distance(p, circle[0])-max(0, circle[1]-9))
        score = travel*0.10 + outside*10 - value
        for enemy, confidence in threats[:8]:
            d = distance(p, enemy["pos"])
            danger = max(0, 200-d)*0.55 + max(0, 65-d)*2.8
            if self.mode == "fight" and self.duel and enemy["id"] == self.duel["id"]:
                # Do not flee a favorable isolated duel while carrying a weapon
                # that needs us to be closer. Stay out of point-blank splash.
                danger = abs(d-self.fight_range)*0.65 + max(0,22-d)*3
            if danger:
                eye = (p[0], p[1], p[2]+me["stats"]["eye_height"])
                ep = enemy["pos"]
                top = (ep[0], ep[1], ep[2]+self.config["mech"]["eye_height"])
                if not self.world.line_clear(eye, top):
                    danger = danger+25 if self.mode == "fight" else danger*0.20
                score += confidence*danger
        # Gently prefer the outer half over the exposed center; never hug a
        # dangerous storm edge. This bias vanishes in the final tiny circles.
        radius = circle[1]
        if radius > 55:
            desired = radius*0.58
            score += abs(distance(p, circle[0])-desired)*0.055
        # Staying still has value when it is already safe.
        if kind == "hide" and travel < 10 and self.mode != "fight":
            score -= 4
        return score

    def choose_goal(self, obs, retreat, threats):
        me, now, zone = obs["self"], obs["t"], obs["zone"]
        p = me["pos"]
        # Rotate early enough to take a route around buildings, not just the
        # straight-line distance. Longer travel needs a longer look-ahead.
        to_next = max(0, distance(p, zone["next_center"])-zone["next_radius"]+18)
        horizon = max(16, min(45, 12+to_next/me["stats"]["walk_speed"]*1.6))
        circle = future_circle(zone, now, horizon)
        radius = max(0, circle[1]-14)
        candidates = [(tuple(p[:2]), "hide", 0)]
        if self.goal:
            candidates.append((self.goal, self.goal_kind, 2))
        candidates.append((tuple(circle[0]), "rotate", 0))
        for ring in (24, 55, 105):
            for i in range(12):
                angle = self.phase+i*math.tau/12
                q = (p[0]+ring*math.cos(angle), p[1]+ring*math.sin(angle))
                candidates.append((clamp_circle(q, circle[0], radius), "hide", 0))
        for i in range(8):
            angle = self.phase+i*math.tau/8
            candidates.append(((circle[0][0]+radius*0.65*math.cos(angle),
                                circle[0][1]+radius*0.65*math.sin(angle)), "rotate", 0))
        nearest_threat = min((distance(p, e["pos"]) for e,c in threats), default=math.inf)
        if self.objective and self.mode == "loot" and nearest_threat > 95:
            category,item_id,expires = self.objective
            item = next((it for it in self.loot.get(category) if it["id"] == item_id),None)
            if item and now < expires and distance(item["pos"],circle[0]) < circle[1]-12:
                if category != "pickups" or all(w is None or w["kind"] != item["kind"] for w in me["weapons"]):
                    return tuple(item["pos"][:2]), self.goal_kind, circle
        if self.duel:
            ep, ev = self.duel["pos"], self.duel.get("vel",[0,0,0])
            away = unit(p[0]-ep[0],p[1]-ep[1])
            for turn in (-0.40,0,0.40):
                a = math.atan2(away[1],away[0])+turn
                candidates.append(((ep[0]+ev[0]*0.25+math.cos(a)*self.fight_range,
                                    ep[1]+ev[1]*0.25+math.sin(a)*self.fight_range), "fight", 28))
        if not retreat and nearest_threat > 95:
            for cube in self.loot.get("cubes"):
                if me["cubes"] < 10 and abs(cube["pos"][2]-self.world.ground(*cube["pos"][:2])) < 4:
                    candidates.append((cube["pos"], "cube", 42))
            held = [w["kind"] for w in me["weapons"] if w]
            second = me["weapons"][1]
            current_value = self.weapon_value(second["kind"]) if second else 0
            for item in self.loot.get("pickups"):
                if item["kind"] not in held and item["kind"] != "gun" and abs(item["pos"][2]-self.world.ground(*item["pos"][:2])) < 4:
                    value = 22*(self.weapon_value(item["kind"])-current_value)
                    if value > 10:
                        candidates.append((item["pos"], "weapon", value))
            for crate in self.loot.get("crates"):
                if me["cubes"] < 10 and distance(p, crate["pos"]) < 100 and abs(crate["pos"][2]-self.world.ground(*crate["pos"][:2])) < 4:
                    candidates.append((crate["pos"], "crate", 30))
            for npc in obs["mechs"]:
                if me["cubes"] < 10 and npc["kind"] == "npc" and distance(p,npc["pos"]) < 100:
                    away = unit(p[0]-npc["pos"][0],p[1]-npc["pos"][1])
                    candidates.append(((npc["pos"][0]+away[0]*48,npc["pos"][1]+away[1]*48),"drone",25))
        # A completed drop restores health: useful, but never run into a crowd.
        if nearest_threat > 85:
            for drop in obs.get("drops", []):
                if drop["lands_in"] < 8 and drop["holder"] in (None, me["id"]) and distance(p, drop["pos"]) < 150:
                    value = 50+65*(1-me["hp"]/me["max_hp"])
                    candidates.append((drop["pos"], "drop", value))
        ranked = []
        for q, kind, value in candidates:
            score = self.goal_score(q, me, circle, threats, kind, value)
            ranked.append((score, tuple(q[:2]), kind))
        score, goal, kind = min(ranked, key=lambda x: x[0])
        category = {"cube":"cubes","weapon":"pickups","crate":"crates"}.get(kind)
        self.objective = None
        if category:
            item = next((it for it in self.loot.get(category) if distance(it["pos"],goal) < 1),None)
            if item:
                self.objective = (category,item["id"],now+12)
        if not math.isfinite(score):
            k = self.nav.nearest(circle[0])
            goal, kind = (self.nav.points[k][:2] if k is not None else tuple(circle[0])), "rotate"
        return goal, kind, circle

    def shelter_circle(self, obs):
        """Use the same detour allowance for cover that ordinary rotation gets."""
        me, zone = obs["self"], obs["zone"]
        remaining = max(0, distance(me["pos"], zone["next_center"])-zone["next_radius"]+18)
        horizon = max(16, min(45, 12+remaining/me["stats"]["walk_speed"]*1.6))
        return future_circle(zone, obs["t"], horizon)

    def steer(self, obs, waypoint, threats, retreat):
        """Roll out bounded motion commands, then retain the existing jet escape."""
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        danger = min((distance(p, e["pos"]) for e, c in threats), default=math.inf)
        zone_ahead = future_circle(obs["zone"], now, 6)
        must_rotate = distance(p, zone_ahead[0]) > zone_ahead[1]-12
        urgent = (not me["in_zone"] or must_rotate or
                  (danger < 80 and self.mode != "fight") or
                  (retreat and now-self.last_damage < 3))
        if self.sprinting:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE
        else:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE+24
        move, self.sprinting = self.motion.choose(
            obs, waypoint, threats, self.mode, self.fight_range, retreat,
            sprinting=self.sprinting, cover=self.cover_active,
            circle=future_circle(obs["zone"], now, 2))
        if (self.last_position is not None and distance(p, self.last_position) < .18
                and distance(p, waypoint) > 8):
            if self.stuck_since is None:
                self.stuck_since = now
        else:
            self.stuck_since = None
        self.last_position = list(p)
        stuck = self.stuck_since is not None and now-self.stuck_since > 1.1
        # A committed ground refuge must not turn into repeated blind jetting.
        # Reject it and let the ordinary planner find a different route instead.
        if self.cover_active and stuck:
            self.cover.reject(self.goal, now)
            self.cover_active = False
            self.goal = None
            self.next_goal = -1
            self.stuck_since = None
        elif (not self.cover_active and (stuck or self.motion.blocked) and
              me["grounded"] and me["energy"] > 58):
            self.jet_until, self.jet_started_z = now+4, p[2]
            self.stuck_since = None
        jet = now < self.jet_until and not me["grounded"] and me["energy"] > 14
        if jet and (p[2]-self.jet_started_z > 35 or me["energy"] < 18):
            self.jet_until = -1
            jet = False
        jump = now < self.jet_until and me["grounded"]
        return move, bool(jet or (self.sprinting and me["grounded"]) or jump), bool(jump)

    def shared_finish_actions(self, obs, action, target, threats):
        """Apply the same reload, upgrade, and nearby pickup policy in every mode."""
        me = obs["self"]
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if gun and gun.get("reload", 0) <= 0:
            # A cooldown or a moment of misalignment is not a reload window.
            quiet = target is None and not any(distance(me["pos"],e["pos"]) < 150 for e,c in threats)
            action["reload"] = gun.get("ammo",0) <= 0 or (quiet and gun.get("ammo",0) < gun["stats"]["mag"]*0.65)
        if obs.get("offer"):
            choices = obs["offer"]["choices"]
            action["pick"] = max(range(len(choices)), key=lambda i: tuning.UPGRADE_VALUE.get(choices[i]["id"], 0))
        held = [w["kind"] for w in me["weapons"] if w]
        second = me["weapons"][1]
        if second is None or second["kind"] == "mortar":
            near = [p for p in obs["pickups"] if p["kind"] not in held and
                    distance(me["pos"],p["pos"]) <= self.config["loot"]["pickup_radius"] and
                    abs(me["pos"][2]-p["pos"][2]) <= 4 and
                    self.weapon_value(p["kind"]) > (self.weapon_value(second["kind"])+0.5 if second else 0)]
            if near:
                action["take"] = max(near, key=lambda p: self.weapon_value(p["kind"]))["id"]
                if second:
                    action["drop"] = 1
        return action

    def act(self, obs):
        self.remember(obs)
        me, now = obs["self"], obs["t"]
        self.nav.set_body(me["stats"])
        old_mode = self.mode
        self.select_mode(obs)
        threats = sorted(self.threats(now), key=lambda ec: distance(me["pos"],ec[0]["pos"]))
        altitude = self.altitude.update(obs, threats, self.shelter_circle(obs),
                                        allow_start=not self.recovering and self.mode != "evade")
        if altitude is not None:
            self.cover.clear("altitude controller owns movement")
            self.cover_active = False
            self.cover_watch_goal = self.cover_watch_position = None
            self.jet_until = -1
            self.stuck_since = None
            self.objective = None
            self.mode, self.duel = "altitude", None
            if "approach" in altitude:
                self.goal, self.goal_kind = tuple(altitude["approach"][:2]), "roof approach"
                waypoint = self.nav.waypoint(me["pos"], self.goal, now,
                                             self.shelter_circle(obs), [])
                move, boost = self.motion.choose(obs, waypoint, threats, "loot", 90, False,
                                                 sprinting=False, cover=False,
                                                 circle=future_circle(obs["zone"], now, 2))
                jump = False
            else:
                self.goal = tuple((self.altitude.exit_goal if self.altitude.phase == "exit" else
                                   (self.altitude.hold_goal or self.altitude.site["hold"]))[:2])
                self.goal_kind = "roof "+str(self.altitude.phase)
                move, boost, jump = altitude["move"], altitude["boost"], altitude["jump"]
            healthy_hold = (self.altitude.phase == "hold" and not self.recovering and
                            me["hp"] >= me["max_hp"]*.90)
            targets = sorted(obs["mechs"], key=lambda e: (e["kind"] != "mech",
                                                         distance(me["pos"], e["pos"])))
            aim, fire, target = (self.combat.action(me, targets, False, obs["alive"] <= 2)
                                 if healthy_hold else (None, [False, False], None))
            if aim is None:
                aim = (aim_at(me["pos"], threats[0][0]["pos"]) if threats else
                       [(self.phase+now*.7+math.pi)%math.tau-math.pi, 0])
            aim[1] = max(me["stats"]["min_pitch"], min(me["stats"]["max_pitch"], aim[1]))
            action = {"tick": obs["tick"], "move": move, "boost": bool(boost),
                      "jump": bool(jump), "aim": aim, "fire": fire}
            self.shared_finish_actions(obs, action, target, threats)
            if self.debug:
                target_point = self.altitude.hold_goal or self.altitude.site["hold"]
                action["debug"] = {"label": "roof/"+str(self.altitude.phase),
                                   "points": [{"at": list(target_point), "color": "#40c0ff"}]}
            return action
        cover_goal = None
        had_cover = self.cover_active
        if self.recovering or self.mode == "evade":
            cover_goal = self.cover.choose(obs, threats, self.shelter_circle(obs),
                                           recovering=self.recovering)
        if cover_goal is not None and self.cover.state == "approach":
            changed = (self.cover_watch_goal is None or
                       distance(cover_goal, self.cover_watch_goal) > 3)
            progressed = (self.cover_watch_position is None or
                          distance(me["pos"], self.cover_watch_position) >= 2)
            if changed or progressed:
                self.cover_watch_goal = cover_goal
                self.cover_watch_position = tuple(me["pos"])
                self.cover_watch_at = now
            elif now-self.cover_watch_at > 3 and distance(me["pos"], cover_goal) > 4:
                self.cover.reject(cover_goal, now)
                cover_goal = None
        else:
            self.cover_watch_goal = self.cover_watch_position = None
            if not (self.recovering or self.mode == "evade"):
                self.cover.clear("healthy or no crossfire")
        self.cover_active = cover_goal is not None
        if self.cover_active:
            self.goal, self.goal_kind = cover_goal, "cover"
            self.objective = None
            self.next_goal = now+tuning.GOAL_INTERVAL
            self.jet_until = -1  # this is a ground refuge, not a flight destination
            if self.recovering:
                self.mode, self.duel = "recover", None
        elif had_cover:
            self.goal = None
            self.next_goal = -1
        retreat = self.recovering and self.mode != "fight"
        if not self.cover_active and (self.goal is None or old_mode != self.mode or
                                      now >= self.next_goal or not me["in_zone"]):
            self.goal, self.goal_kind, self.circle = self.choose_goal(obs, retreat, threats)
            self.next_goal = now+tuning.GOAL_INTERVAL
        circle = future_circle(obs["zone"], now, 12)
        waypoint = self.nav.waypoint(me["pos"], self.goal, now, circle,
                                     [e["pos"] for e,c in threats[:5]])
        move, boost, jump = self.steer(obs, waypoint, threats, retreat)
        targets = sorted(obs["mechs"], key=lambda e: (e["kind"] != "mech", distance(me["pos"],e["pos"])))
        if not retreat and (not threats or distance(me["pos"],threats[0][0]["pos"]) > 110):
            # Crate farming only when quiet and close enough to collect the cube.
            targets += sorted((c for c in self.loot.get("crates") if distance(me["pos"],c["pos"]) < 110),
                              key=lambda c: distance(me["pos"],c["pos"]))
        # Healing is already interrupted under fire. Answer with the gun briefly,
        # preserving movement speed and energy; stop once incoming hits cease.
        return_fire = now-self.last_weapon_damage < 1.0
        aim, fire, target = self.combat.action(me, targets, retreat, obs["alive"] <= 2,
                                             return_fire=return_fire)
        if self.cover_active and self.cover.sheltered and self.recovering:
            # A weak target or an over-wall mortar must not restart the healing
            # clock. Trigger-off releases any already-held laser into the cover.
            aim, fire, target = None, [False, False], None
        if aim is None:
            # Face the nearest threat even while running the other way: rear hits
            # hurt 50% more. When quiet, periodically scan all directions.
            if threats:
                e = threats[0][0]
                aim = aim_at(me["pos"], e["pos"])
            else:
                aim = [(self.phase+now*0.7+math.pi)%math.tau-math.pi, 0.0]
            damaged = [e for e in obs["events"] if e["type"] == "damaged" and e.get("bearing") is not None]
            if damaged:
                aim = [damaged[-1]["bearing"], 0.0]
        action = {"tick": obs["tick"], "move": move, "boost": boost,
                  "jump": jump, "aim": aim, "fire": fire}
        self.shared_finish_actions(obs, action, target, threats)
        if self.debug:
            debug_goal = self.goal or me["pos"][:2]
            action["debug"] = {"label": f"{self.mode}/{self.goal_kind} | HP {me['hp']:.0f}",
                               "points": [{"at": [*debug_goal,self.world.ground(*debug_goal)], "color":"#40c0ff"}]}
        return action
