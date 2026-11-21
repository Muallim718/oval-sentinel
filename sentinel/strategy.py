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
from .cover import CoverPlanner
from .movement import GroundSteering
from .salvage import KillSalvage
from .opener import Opener
from .duel_commitment import DuelCommitment
from .quiet_window import QuietWindow
from .reload_arm import ReloadArm
from .upgrade_economy import UpgradeEconomy
from .sound import SoundScout


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
        self.salvage = KillSalvage(self.world, self.config)
        self.opener = Opener(self.world, self.config)
        self.commitment = DuelCommitment(self.config)
        self.quiet_window = QuietWindow(self.config)
        self.reload_arm = ReloadArm(self.world, self.config)
        self.arm_active = False
        self.upgrade_economy = UpgradeEconomy(self.config, tuning.UPGRADE_VALUE)
        self.sound = SoundScout(self.config)
        self.motion = GroundSteering(self.world, self.config)
        self.cover_active = False
        self.cover_watch_goal = None
        self.cover_watch_position = None
        self.cover_watch_at = -1
        self.seen = {}
        self.goal, self.goal_kind = None, "rotate"
        self.next_goal = -1
        self.last_damage = -100
        self.last_weapon_damage = -100
        self.recent_attackers = {}
        self.incoming_hint = None
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
                    attacker = event.get("by")
                    if isinstance(attacker, int) and 0 <= attacker < 16:
                        self.recent_attackers[attacker] = now
            elif event["type"] == "kill":
                self.salvage.record_kill(now, event["target"], self.seen.get(event["target"]))
                self.seen.pop(event["target"], None)
                self.recent_attackers.pop(event["target"], None)
                if self.incoming_hint and event["target"] == self.incoming_hint[1]:
                    self.incoming_hint = None
        eliminated = {event["target"] for event in obs["events"] if event["type"] == "kill"}
        incoming = [event for event in obs["events"] if event["type"] == "damaged" and
                    event.get("bearing") is not None and isinstance(event.get("by"), int) and
                    0 <= event["by"] < 16 and event["by"] not in eliminated]
        if incoming:
            strongest = max(incoming, key=lambda event: event["amount"])
            self.incoming_hint = (now, strongest["by"], strongest["bearing"])
        self.seen = {k:v for k,v in self.seen.items() if now-v[0] < tuning.THREAT_MEMORY}

    def threats(self, now):
        return [(enemy, max(0.25, 1-(now-last)/tuning.THREAT_MEMORY))
                for last, enemy in self.seen.values()]

    def active_enemy_ids(self, obs):
        """Answer observed aggression before starting an optional mech fight."""
        me, now = obs["self"], obs["t"]
        active = set()
        for enemy in obs["mechs"]:
            if enemy["kind"] != "mech":
                continue
            ident = enemy["id"]
            p, ep = me["pos"], enemy["pos"]
            dx, dy = p[0]-ep[0], p[1]-ep[1]
            d = max(.01, math.hypot(dx, dy))
            facing = abs(angle_error(enemy["aim"][0], math.atan2(dy, dx)))
            vx, vy = enemy.get("vel", (0, 0, 0))[:2]
            closing = (vx*dx+vy*dy)/d
            if (obs["alive"] <= 2 or d < 19 or enemy.get("hp", 1400) <= 135 or
                    now-self.recent_attackers.get(ident, -100) < 12 or
                    (d <= 200 and facing <= .39) or
                    (d <= 110 and closing >= 5 and facing <= 1.2)):
                active.add(ident)
        return active

    @staticmethod
    def weapon_value(kind):
        return {"laser": 3.0, "lightning": 3.0, "mortar": 1.0, "gun": 0.0}.get(kind, 0)

    def select_mode(self, obs, active=None):
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
        elif exposed and (active is None or exposed[0]["id"] in active):
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

    def steer(self, obs, waypoint, threats, retreat, closing=False):
        """Roll out bounded motion commands, then retain the existing jet escape."""
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        danger = min((distance(p, e["pos"]) for e, c in threats), default=math.inf)
        zone_ahead = future_circle(obs["zone"], now, 6)
        must_rotate = distance(p, zone_ahead[0]) > zone_ahead[1]-12
        urgent = (closing or not me["in_zone"] or must_rotate or
                  (danger < 80 and self.mode != "fight") or
                  (retreat and now-self.last_damage < 3))
        if self.mode == "salvage":
            self.sprinting = self.salvage.sprint and me["grounded"]
        elif self.sprinting:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE
        else:
            self.sprinting = urgent and me["energy"] > tuning.ENERGY_RESERVE+24
        move, self.sprinting = self.motion.choose(
            obs, waypoint, threats, self.mode, self.fight_range, retreat,
            sprinting=self.sprinting, cover=self.cover_active,
            circle=future_circle(obs["zone"], now, 2))
        if self.mode == "salvage":
            # The pickup race already checked a ground corridor and sprint
            # reserve. Never introduce a blind jet on this short commitment.
            self.stuck_since = None
            self.last_position = list(p)
            return move, bool(self.sprinting and me["grounded"]), False
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

    def act(self, obs):
        self.remember(obs)
        self.quiet_window.update(obs)
        self.sound.update(obs)
        me, now = obs["self"], obs["t"]
        self.nav.set_body(me["stats"])
        old_mode = self.mode
        active = self.active_enemy_ids(obs)
        self.select_mode(obs, active)
        threats = sorted(self.threats(now), key=lambda ec: distance(me["pos"],ec[0]["pos"]))
        self.reload_arm.update(obs)
        salvage_goal = self.salvage.choose(
            obs, self.loot.get("cubes"), threats, self.shelter_circle(obs),
            emergency=not me["in_zone"] or
            (me["hp"] < me["max_hp"]*.23 and now-self.last_weapon_damage < .6))
        previous_commitment = self.commitment.target_id
        repairing = self.recovering and self.quiet_window.repair(
            obs, sheltered=self.cover_active and self.cover.sheltered and me["grounded"])
        if repairing and self.mode == "fight":
            self.mode, self.duel = "recover", None
        fight_obs = dict(obs, mechs=[e for e in obs["mechs"] if e["id"] in active])
        duel = self.commitment.choose(fight_obs, threats, future_circle(obs["zone"], now, 10),
                                      self.world, sheltered=repairing)
        if salvage_goal is not None:
            duel = None
        if duel is not None:
            self.mode, self.duel = "fight", duel.enemy
            self.fight_range = duel.range
        if previous_commitment != self.commitment.target_id:
            self.next_goal = -1
        opening = None
        charging = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])
        if salvage_goal is None and duel is None and not charging:
            opening = self.opener.choose(obs, threats, self.shelter_circle(obs),
                                         recovering=self.recovering)
        elif self.opener.current is not None:
            self.opener.cancel("existing combat action takes priority")
        arming = None
        had_arming = self.arm_active
        if salvage_goal is None and opening is None and not charging and not repairing:
            arming = self.reload_arm.choose(obs, threats, self.shelter_circle(obs),
                                            recovering=self.recovering)
        elif self.reload_arm.current is not None:
            self.reload_arm.cancel("higher priority resource or held combat action")
        self.arm_active = arming is not None
        cover_goal = None
        had_cover = self.cover_active
        if (salvage_goal is None and opening is None and arming is None and duel is None and
                (self.recovering or self.mode == "evade")):
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
        if salvage_goal is not None:
            self.cover.clear("collecting confirmed kill reward")
            self.mode, self.duel = "salvage", None
            self.goal, self.goal_kind = salvage_goal, "kill cubes"
            self.next_goal = now+tuning.GOAL_INTERVAL
            self.objective = None
            self.jet_until = -1
        elif opening is not None:
            self.cover.clear("opening power mission owns the route")
            self.mode, self.duel = "opening", None
            self.goal, self.goal_kind = tuple(opening.goal[:2]), opening.kind
            self.next_goal = now+tuning.GOAL_INTERVAL
            self.objective = None
            self.jet_until = -1
        elif arming is not None:
            self.cover.clear("short reload equipment route owns movement")
            self.goal, self.goal_kind = tuple(arming.goal[:2]), "reload weapon"
            self.next_goal = now+tuning.GOAL_INTERVAL
            self.objective = None
            self.jet_until = -1
        elif self.cover_active:
            self.goal, self.goal_kind = cover_goal, "cover"
            self.objective = None
            self.next_goal = now+tuning.GOAL_INTERVAL
            self.jet_until = -1  # this is a ground refuge, not a flight destination
            if self.recovering:
                self.mode, self.duel = "recover", None
        elif had_cover or had_arming:
            self.goal = None
            self.next_goal = -1
        retreat = self.recovering and self.mode != "fight"
        if (salvage_goal is None and opening is None and arming is None and not self.cover_active and
                (self.goal is None or old_mode != self.mode or now >= self.next_goal or not me["in_zone"])):
            self.goal, self.goal_kind, self.circle = self.choose_goal(obs, retreat, threats)
            self.next_goal = now+tuning.GOAL_INTERVAL
        circle = future_circle(obs["zone"], now, 12)
        if opening is not None:
            waypoint = opening.waypoint or opening.goal
            move, boost = self.motion.choose(obs, waypoint, threats, "opening", 75, False,
                                             sprinting=opening.sprint, cover=False,
                                             circle=future_circle(obs["zone"], now, 2))
            jump, self.sprinting = False, boost
            self.stuck_since = None
            self.last_position = list(me["pos"])
        elif arming is not None:
            if arming.move is not None:
                move, boost = list(arming.move), False
            else:
                move, boost = self.motion.choose(obs, arming.waypoint, threats, "salvage", 75, False,
                                                 sprinting=False, cover=False,
                                                 circle=future_circle(obs["zone"], now, 2))
            jump, self.sprinting = False, boost
            self.stuck_since = None
            self.last_position = list(me["pos"])
        else:
            waypoint = salvage_goal or self.nav.waypoint(
                me["pos"], self.goal, now, circle, [e["pos"] for e,c in threats[:5]])
            move, boost, jump = self.steer(obs, waypoint, threats, retreat, closing=bool(duel and duel.sprint))
        targets = sorted((e for e in obs["mechs"] if e["kind"] != "mech" or e["id"] in active),
                         key=lambda e: (e["kind"] != "mech", distance(me["pos"],e["pos"])))
        if opening is not None:
            targets = [opening.exclusive_target] if opening.exclusive_target else []
        elif duel is not None:
            targets = [duel.enemy]
        elif not retreat and (not threats or distance(me["pos"],threats[0][0]["pos"]) > 110):
            # Crate farming only when quiet and close enough to collect the cube.
            targets += sorted((c for c in self.loot.get("crates") if distance(me["pos"],c["pos"]) < 110),
                              key=lambda c: distance(me["pos"],c["pos"]))
        # Escape movement and attack permission are independent. Actual
        # shelter or continuing regeneration takes priority over a viable shot.
        repairing = self.recovering and self.quiet_window.repair(
            obs, sheltered=self.cover_active and self.cover.sheltered and me["grounded"])
        attack_retreat = retreat
        if retreat and active and not repairing:
            targets = [target for target in targets if target["kind"] == "mech"]
            attack_retreat = False
        return_fire = now-self.last_weapon_damage < 1.0
        aim, fire, target = self.combat.action(me, targets, attack_retreat, obs["alive"] <= 2,
                                             return_fire=return_fire,
                                             forced_weapon="gun" if opening is not None else None)
        if repairing:
            # A weak target or an over-wall mortar must not restart the healing
            # clock. Trigger-off releases any already-held laser into the cover.
            aim, fire, target = None, [False, False], None
        if aim is None:
            # Face the nearest threat even while running the other way: rear hits
            # hurt 50% more. When quiet, periodically scan all directions.
            if threats:
                e = threats[0][0]
                aim = aim_at(me["pos"], e["pos"])
            elif opening is not None:
                aim = aim_at(me["pos"], opening.goal)
            else:
                scan = self.sound.heading(now)
                if scan is None:
                    scan = self.opener.scan_yaw(obs, threats)
                aim = [scan if scan is not None else (self.phase+now*0.7+math.pi)%math.tau-math.pi, 0.0]
            damaged = [e for e in obs["events"] if e["type"] == "damaged" and e.get("bearing") is not None]
            if damaged:
                aim = [damaged[-1]["bearing"], 0.0]
            elif self.incoming_hint and now-self.incoming_hint[0] < 1.1:
                # At 4 rad/s, turning all the way around takes almost .8 s.
                # Give incoming fire time to enter the actual torso's view.
                aim = [self.incoming_hint[2], 0.0]
        action = {"tick": obs["tick"], "move": move, "boost": boost,
                  "jump": jump, "aim": aim, "fire": fire}
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if gun and gun.get("reload", 0) <= 0:
            # A cooldown or a moment of misalignment is not a reload window.
            quiet = target is None and not any(distance(me["pos"],e["pos"]) < 150 for e,c in threats)
            action["reload"] = gun.get("ammo",0) <= 0 or (quiet and gun.get("ammo",0) < gun["stats"]["mag"]*0.65)
        if obs.get("offer"):
            pick = self.upgrade_economy.choose(obs, target=self.duel, recovering=self.recovering,
                                               sheltered=repairing)
            if pick is not None:
                action["pick"] = pick
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
        if arming is not None and arming.take is not None and second is None:
            action["take"] = arming.take
        if self.debug:
            debug_goal = self.goal or me["pos"][:2]
            action["debug"] = {"label": f"{self.mode}/{self.goal_kind} | HP {me['hp']:.0f}",
                               "points": [{"at": [*debug_goal,self.world.ground(*debug_goal)], "color":"#40c0ff"}]}
        return action
