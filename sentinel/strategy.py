"""The decision loop, in priority order: survive zone, escape, recover, loot, fight.

No private seeds, engine internals, or knowledge of unseen objects are used.
"""
import math
import os
import random
from pathlib import Path
from . import tuning
from .combat import Combat, aim_at
from .geometry import World, angle_error, distance, unit
from .navigation import Navigator
from .memory import LootMemory


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
        self.seen = {}
        self.goal, self.goal_kind = None, "rotate"
        self.next_goal = -1
        self.last_damage = -100
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

    def steer(self, obs, waypoint, threats, retreat):
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        desired = unit(waypoint[0]-p[0], waypoint[1]-p[1])
        # A small orbit makes aim prediction harder while keeping zone progress.
        nearby = [(e,c) for e,c in threats if distance(p,e["pos"]) < 140]
        if nearby:
            e = min(nearby, key=lambda ec: distance(p, ec[0]["pos"]))[0]
            away = unit(p[0]-e["pos"][0], p[1]-e["pos"][1])
            d = distance(p, e["pos"])
            preferred = self.fight_range if self.mode == "fight" else tuning.PREFERRED_DISTANCE
            force = max(-0.8 if self.mode == "fight" else 0, min(1.6,(preferred-d)/40))
            orbit = math.sin(now*1.7+self.phase)
            desired = unit(desired[0]+away[0]*force-away[1]*orbit*0.80,
                           desired[1]+away[1]*force+away[0]*orbit*0.80)
        if distance(p, waypoint) < 3 and not nearby:
            return [0.0, 0.0], False, False
        danger = min((distance(p,e["pos"]) for e,c in nearby), default=math.inf)
        zone_ahead = future_circle(obs["zone"],now,6)
        must_rotate = distance(p,zone_ahead[0]) > zone_ahead[1]-12
        urgent = not me["in_zone"] or must_rotate or (danger < 80 and self.mode != "fight") or (retreat and now-self.last_damage < 3)
        if self.sprinting:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE
        else:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE+24
        speed = stats["boost_speed"] if self.sprinting else stats["walk_speed"]
        travel = speed*0.45
        angle = math.atan2(desired[1], desired[0])
        best = None
        circle = future_circle(obs["zone"], now, 2)
        projectiles = sorted(obs["projectiles"], key=lambda pr: distance(p,pr["pos"]))[:12]
        for offset in (0, 0.35, -0.35, 0.7, -0.7, 1.1, -1.1, 1.65, -1.65, math.pi):
            yaw = angle+offset
            move = (math.cos(yaw), math.sin(yaw))
            # Include acceleration inertia in the near-term forecast.
            q = (p[0]+move[0]*travel+me["vel"][0]*0.10,
                 p[1]+move[1]*travel+me["vel"][1]*0.10, p[2])
            if not self.world.walk_clear(p, q, stats["radius"]+0.3, stats["height"],
                                         stats["step_up"], stats["max_slope_deg"]):
                continue
            score = distance(q, waypoint)*0.8 + abs(offset)*1.3
            score += max(0, distance(q,circle[0])-circle[1]+4)*12
            for enemy,c in nearby[:6]:
                d = distance(q,enemy["pos"])
                if self.mode == "fight":
                    score += abs(d-self.fight_range)*0.30*c + max(0,20-d)*2
                else:
                    score += max(0, 75-d)*(1.4 if retreat else 0.8)*c
                if enemy.get("charging"):
                    ep = enemy["pos"]
                    bearing = math.atan2(q[1]-ep[1],q[0]-ep[0])
                    score += max(0, 1-abs(angle_error(bearing,enemy["aim"][0]))/0.12)*14
            # Predict closest approach to moving bullets/shells over 0.45 s.
            for projectile in projectiles:
                pp, v = projectile["pos"], projectile["vel"]
                rx, ry = pp[0]-p[0], pp[1]-p[1]
                vx, vy = v[0]-move[0]*speed, v[1]-move[1]*speed
                t = max(0, min(0.45, -(rx*vx+ry*vy)/(vx*vx+vy*vy or 1)))
                d = math.hypot(rx+vx*t, ry+vy*t)
                z = pp[2]+v[2]*t
                if projectile["kind"] == "mortar":
                    z -= self.config["weapons"]["mortar"]["gravity"]*t*t/2
                if p[2]-3 < z < p[2]+stats["height"]+4:
                    radius = stats["radius"]+(7 if projectile["kind"] == "mortar" else 1)
                    score += max(0, radius+3-d)*7
            if best is None or score < best[0]:
                best = score, move
        if self.last_position is not None and distance(p,self.last_position) < 0.18 and distance(p,waypoint) > 8:
            if self.stuck_since is None:
                self.stuck_since = now
        else:
            self.stuck_since = None
        self.last_position = list(p)
        stuck = self.stuck_since is not None and now-self.stuck_since > 1.1
        if (stuck or best is None) and me["grounded"] and me["energy"] > 58:
            self.jet_until, self.jet_started_z = now+4, p[2]
            self.stuck_since = None
        jet = now < self.jet_until and not me["grounded"] and me["energy"] > 14
        if jet and (p[2]-self.jet_started_z > 35 or me["energy"] < 18):
            self.jet_until = -1
            jet = False
        jump = now < self.jet_until and me["grounded"]
        move = list(best[1]) if best else list(desired)
        return move, bool(jet or (self.sprinting and me["grounded"]) or jump), bool(jump)

    def act(self, obs):
        self.remember(obs)
        me, now = obs["self"], obs["t"]
        self.nav.set_body(me["stats"])
        old_mode = self.mode
        self.select_mode(obs)
        threats = sorted(self.threats(now), key=lambda ec: distance(me["pos"],ec[0]["pos"]))
        retreat = self.recovering and self.mode != "fight"
        if self.goal is None or old_mode != self.mode or now >= self.next_goal or not me["in_zone"]:
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
        aim, fire, target = self.combat.action(me, targets, retreat, obs["alive"] <= 2)
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
        if self.debug:
            action["debug"] = {"label": f"{self.mode}/{self.goal_kind} | HP {me['hp']:.0f}",
                               "points": [{"at": [*self.goal,self.world.ground(*self.goal)], "color":"#40c0ff"}]}
        return action
