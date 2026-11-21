"""Spend a short sprint only when it removes a real imminent gun contact.

Ordinary steering, aiming and weapon choices belong to the caller. The dodge
owns a fixed direction for at most four 10Hz decisions, with live safety vetoes.
"""
import math
import time

from .geometry import angle_error, distance, unit


class ImpactBoost:
    BUDGET = .0025  # leave overhead around the strictly bounded search
    HORIZON = .60
    IMMINENT = .45
    HOLD_SECONDS = .35
    MAX_PROJECTILES = 6

    def __init__(self, world, config, reserve=26):
        self.world, self.config, self.reserve = world, config, reserve
        self.active_until = -1.0
        self.command = None
        self.reason = "ordinary movement"
        self.charge_clear_until = -1.0

    def cancel(self, reason):
        self.active_until, self.command, self.reason = -1, None, reason

    def _schedules(self, me, fire, now):
        laser = next(((slot, w) for slot, w in enumerate(me["weapons"])
                      if w and w["kind"] == "laser"), None)
        if laser is None:
            return [(1, 1, 0)]
        if fire is None:
            return None  # the caller must tell us whether charging starts/stops
        slot, weapon = laser
        charge = weapon.get("charge", 0)
        if charge <= 0:
            self.charge_clear_until = -1
        elif charge < weapon["stats"]["charge"]-.001:
            self.charge_clear_until = max(self.charge_clear_until, now+
                weapon["stats"]["charge"]-charge+weapon["stats"]["hold_s"])
        slow = me["stats"].get("charge_move_mult", .5)
        if charge > 0 and fire[slot]:
            if charge >= weapon["stats"]["charge"]-.001:
                if now+self.HORIZON >= self.charge_clear_until:
                    return None  # capped reports hide an unobserved hold clock
            return [(slow, slow, 0)]
        if charge > 0:
            release = max(0, weapon["stats"]["min_charge"]-charge)
            release = math.ceil(release/.05-1e-9)*.05
            return [(slow, 1, release), (slow, 1, release+.05)]
        if fire[slot]:
            start = math.ceil(max(0, weapon.get("cooldown", 0))/.05-1e-9)*.05
            return [(1, slow, start), (1, slow, start+.05)]
        return [(1, 1, 0)]

    def _energy(self, me, seconds):
        expenditure = me["stats"]["boost_drain"]*seconds
        for weapon in me["weapons"]:
            if weapon and weapon["kind"] == "lightning":
                expenditure += math.ceil(seconds/weapon["stats"]["cooldown"])*weapon["stats"]["energy"]
        return me["energy"]-expenditure >= self.reserve+1

    def _projectiles(self, obs):
        me = obs["self"]
        reach_speed = max(me["stats"]["boost_speed"], math.hypot(*me["vel"][:2]))
        candidates = []
        gun_count = 0
        for index, projectile in enumerate(obs["projectiles"]):
            if index >= 64:
                return None
            if projectile["kind"] != "gun":
                # This isolated controller must not dodge a gun into an
                # unmodelled nearby mortar blast or drone round.
                limit = 65 if projectile["kind"] == "mortar" else 75
                if distance(me["pos"], projectile["pos"]) < limit:
                    return None
                continue
            gun_count += 1
            if gun_count > 64:
                return None
            p, velocity = projectile["pos"], projectile["vel"]
            dx, dy = p[0]-me["pos"][0], p[1]-me["pos"][1]
            speed_sq = velocity[0]**2+velocity[1]**2
            if speed_sq < 1:
                continue
            when = max(0, min(self.HORIZON, -(dx*velocity[0]+dy*velocity[1])/speed_sq))
            if dx*velocity[0]+dy*velocity[1] >= 0 and math.hypot(dx, dy) > me["stats"]["radius"]+1:
                continue
            if math.hypot(dx+velocity[0]*when, dy+velocity[1]*when) > reach_speed*when+me["stats"]["radius"]+2:
                continue
            candidates.append((when, projectile))
        if len(candidates) > self.MAX_PROJECTILES:
            return None
        return [projectile for _, projectile in sorted(candidates, key=lambda pair: pair[0])]

    def _rollout(self, me, command, boosting, ordinary_move, ordinary_boost,
                 duration, schedule, circle, deadline):
        stats = me["stats"]
        p = list(me["pos"])
        vx, vy = me["vel"][:2]
        path = [tuple(p)]
        for step in range(1, 13):
            if time.perf_counter() >= deadline:
                return None
            elapsed = (step-1)*.05
            held = elapsed < duration-1e-9
            move, boost = (command, boosting) if held else (ordinary_move, ordinary_boost)
            multiplier = schedule[0] if elapsed < schedule[2]-1e-9 else schedule[1]
            speed = stats["boost_speed"] if boost else stats["walk_speed"]
            dx, dy = move[0]*speed*multiplier-vx, move[1]*speed*multiplier-vy
            ratio = min(1, stats["ground_accel"]*.05/max(1e-9, math.hypot(dx, dy)))
            vx, vy = vx+dx*ratio, vy+dy*ratio
            q = [p[0]+vx*.05, p[1]+vy*.05, 0]
            q[2] = self.world.ground(*q[:2])
            if (distance(q, circle[0]) > circle[1]-stats["radius"]-1 or
                    not self.world.walk_clear(p, q, stats["radius"]+.3, stats["height"],
                                              stats["step_up"], stats["max_slope_deg"]) or
                    not self.world.body_clear(*q, stats["radius"]+.3, stats["height"], 0)):
                return None
            path.append(tuple(q))
            p = q
        return path

    def _contacts(self, obs, path, projectiles, deadline, margin=0):
        radius = obs["self"]["stats"]["radius"]+margin
        height = obs["self"]["stats"]["height"]
        contacts = []
        for projectile in projectiles:
            p, velocity = projectile["pos"], projectile["vel"]
            for step in range(1, len(path)):
                if time.perf_counter() >= deadline:
                    return None
                start, end = (step-1)*.05, step*.05
                before = [p[i]+velocity[i]*start for i in range(3)]
                after = [p[i]+velocity[i]*end for i in range(3)]
                rx, ry = before[0]-path[step-1][0], before[1]-path[step-1][1]
                dx = after[0]-before[0]-(path[step][0]-path[step-1][0])
                dy = after[1]-before[1]-(path[step][1]-path[step-1][1])
                a, b, c = dx*dx+dy*dy, 2*(rx*dx+ry*dy), rx*rx+ry*ry-radius*radius
                if a < 1e-12:
                    interval = (0, 1) if c <= 0 else None
                else:
                    disc = b*b-4*a*c
                    if disc < 0:
                        continue
                    root = math.sqrt(disc)
                    lo, hi = max(0, (-b-root)/(2*a)), min(1, (-b+root)/(2*a))
                    interval = (lo, hi) if lo <= hi else None
                if interval is None:
                    continue
                z0 = before[2]-path[step-1][2]
                dz = after[2]-before[2]-(path[step][2]-path[step-1][2])
                lo, hi = interval
                if abs(dz) < 1e-12:
                    if not -margin/2 <= z0 <= height+margin/2:
                        continue
                else:
                    z1, z2 = (-margin/2-z0)/dz, (height+margin/2-z0)/dz
                    lo, hi = max(lo, min(z1, z2)), min(hi, max(z1, z2))
                    if lo > hi:
                        continue
                point = [before[i]+(after[i]-before[i])*lo for i in range(3)]
                if self.world.line_clear(p, point):
                    contacts.append((projectile["id"], start+.05*lo))
                break  # blocked before this crossing means it cannot hit later
        return contacts

    def choose(self, obs, move, boost, *, circle=None, sheltered=False, fire=None):
        me, now = obs["self"], obs["t"]
        ordinary = (move, boost)
        circle = circle or (obs["zone"]["center"], obs["zone"]["radius"])
        deadline = time.perf_counter()+self.BUDGET
        if (not me["grounded"] or not me["in_zone"] or sheltered or
                abs(me["pos"][2]-self.world.ground(*me["pos"][:2])) > .2):
            self.cancel("ordinary shelter, terrain, or storm control takes priority")
            return ordinary
        schedules = self._schedules(me, fire, now)
        projectiles = self._projectiles(obs)
        if schedules is None or projectiles is None:
            self.cancel("unmodelled charge timing or projectile crowd")
            return ordinary
        active = self.command is not None and now < self.active_until
        duration = min(.4, max(.1, self.active_until-now+.05)) if active else .4
        if not self._energy(me, duration):
            self.cancel("preserve the live emergency energy reserve")
            return ordinary
        base_contacts = []
        for schedule in schedules:
            path = self._rollout(me, move, boost, move, boost, self.HORIZON, schedule, circle, deadline)
            if path is None:
                self.cancel("ordinary path cannot be safely forecast within budget")
                return ordinary
            contacts = self._contacts(obs, path, projectiles, deadline)
            if contacts is None:
                self.cancel("projectile forecast budget exhausted")
                return ordinary
            base_contacts.append(contacts)
        if not active and (not projectiles or not all(any(eta <= self.IMMINENT for _, eta in contacts)
                                                     for contacts in base_contacts)):
            self.reason = "ordinary movement already avoids imminent gun contacts"
            return ordinary
        if active:
            commands = [self.command]
        else:
            first_id = min((hit for contacts in base_contacts for hit in contacts), key=lambda hit: hit[1])[0]
            projectile = next(projectile for projectile in projectiles if projectile["id"] == first_id)
            vx, vy = projectile["vel"][:2]
            perpendicular = unit(-vy, vx)
            proposed = [unit(*move), perpendicular, (-perpendicular[0], -perpendicular[1])]
            angle = math.atan2(perpendicular[1], perpendicular[0])
            proposed += [(math.cos(angle+a), math.sin(angle+a)) for a in (.35, -.35)]
            commands = []
            for command in proposed:
                if command != (0, 0) and all(distance(command, old) > .05 for old in commands):
                    commands.append(command)
        best = None
        for command in commands[:5]:
            risks, candidate_contacts, valid = [], [], True
            for schedule in schedules:
                path = self._rollout(me, command, True, move, boost, duration, schedule, circle, deadline)
                contacts = self._contacts(obs, path, projectiles, deadline, margin=.4) if path else None
                if contacts is None:
                    valid = False
                    break
                risks.append(len(contacts))
                candidate_contacts.append(contacts)
            if not valid:
                if time.perf_counter() >= deadline:
                    break
                continue
            safe = (all({ident for ident, _ in contacts}.issubset({ident for ident, _ in base})
                        for contacts, base in zip(candidate_contacts, base_contacts)) if active else
                    all(risk == 0 for risk in risks))
            if not safe:
                continue
            deviation = abs(angle_error(math.atan2(command[1], command[0]), math.atan2(move[1], move[0])))
            score = max(risks), sum(risks), deviation
            if best is None or score < best[0]:
                best = score, command
        if best is None:
            self.cancel("no completely checked boost path reduces contact")
            return ordinary
        if not active:
            self.active_until = now+self.HOLD_SECONDS
            self.command = list(best[1])
        self.reason = "short boost removes an imminent gun contact" if not active else "finish the checked boost sidestep"
        return list(best[1]), True
