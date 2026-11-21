"""Intercept aiming and trigger discipline. Both slots share one torso aim."""
import math
import time
from .geometry import angle_error, distance


def intercept(origin, target, velocity, speed):
    """Time until a constant-speed shot meets a constant-velocity target."""
    r = [target[i]-origin[i] for i in range(3)]
    a = sum(v*v for v in velocity)-speed*speed
    b = 2*sum(r[i]*velocity[i] for i in range(3))
    c = sum(v*v for v in r)
    if abs(a) < 1e-9:
        t = -c/b if abs(b) > 1e-9 else 0
        return max(0.0, t)
    discriminant = b*b-4*a*c
    if discriminant < 0:
        return 0.0
    roots = [(-b-math.sqrt(discriminant))/(2*a), (-b+math.sqrt(discriminant))/(2*a)]
    return min((t for t in roots if t >= 0), default=0.0)


def aim_at(origin, target):
    return [math.atan2(target[1]-origin[1], target[0]-origin[0]),
            math.atan2(target[2]-origin[2], distance(origin, target))]


def target_center(target, config):
    kind = target.get("kind", "crate")
    if kind == "mech":
        scale = 1 + config["cubes"].get("size_per_cube", 0.05)*target.get("cubes", 0)
        height, radius = config["mech"]["height"]*scale, config["mech"]["radius"]*scale
    else:
        stats = config["npc"] if kind == "npc" else config["crates"]
        height, radius = stats.get("height", 3.5), stats.get("radius", 1.4)
    p = target["pos"]
    return [p[0], p[1], p[2]+height*0.5], radius, height


class ExposedSolution(tuple):
    """The usual four fields, plus the body behind an off-center aim point."""
    def __new__(cls, aim, point, radius, height, center, velocity, flight):
        result = super().__new__(cls, (aim, point, radius, height))
        result.center = center
        result.velocity = velocity
        result.flight = flight
        return result


def cylinder_entry(origin, direction, center, radius, height, limit):
    """First distance on a ray inside a finite, vertical body cylinder."""
    dx, dy = origin[0]-center[0], origin[1]-center[1]
    a = direction[0]**2+direction[1]**2
    b = 2*(dx*direction[0]+dy*direction[1])
    c = dx*dx+dy*dy-radius*radius
    if a < 1e-12:
        if c > 0:
            return None
        lo, hi = 0, limit
    else:
        disc = b*b-4*a*c
        if disc < 0:
            return None
        root = math.sqrt(disc)
        lo, hi = max(0, (-b-root)/(2*a)), min(limit, (-b+root)/(2*a))
    bottom, top = center[2]-height/2+.15, center[2]+height/2-.15
    if abs(direction[2]) < 1e-12:
        if not bottom <= origin[2] <= top:
            return None
    else:
        z1, z2 = (bottom-origin[2])/direction[2], (top-origin[2])/direction[2]
        lo, hi = max(lo, min(z1, z2)), min(hi, max(z1, z2))
    return lo if lo <= hi else None


class Combat:
    EXPOSED_SECONDS = .003

    def __init__(self, world, config):
        self.world, self.config = world, config
        self.locked_id = None

    def solve(self, me, target, weapon):
        return self._solve(me, target, weapon, time.perf_counter()+self.EXPOSED_SECONDS)

    def _exposed(self, me, target, weapon, origin, radius, height, deadline):
        """Try a small interior silhouette only when the original ray is blocked."""
        if target.get("kind") not in ("mech", "npc"):
            return None
        center, _, _ = target_center(target, self.config)
        dx, dy = center[0]-origin[0], center[1]-origin[1]
        length = max(1e-9, math.hypot(dx, dy))
        side = (-dy/length*radius, dx/length*radius)
        velocity = target.get("vel", [0, 0, 0])
        stats = weapon["stats"]
        # Upper center, two middle flanks, then two upper flanks. Each sample
        # stays inside the body rather than betting on a mathematical tangent.
        for lateral, fraction in ((0, .90), (.72, .55), (-.72, .55),
                                  (.58, .86), (-.58, .86)):
            if time.perf_counter() >= deadline:
                return None
            offset = (side[0]*lateral, side[1]*lateral, height*(fraction-.5))
            sample = [center[i]+offset[i] for i in range(3)]
            flight = intercept(origin, sample, velocity, stats["speed"]) if weapon["kind"] == "gun" else 0
            predicted = [center[i]+velocity[i]*flight for i in range(3)]
            if weapon["kind"] == "gun" and abs(velocity[2]) > .5:
                predicted[2] -= self.config["mech"]["gravity"]*flight*flight/2
                predicted[2] = max(predicted[2], self.world.ground(*predicted[:2])+height/2)
            point = [predicted[i]+offset[i] for i in range(3)]
            aim = aim_at(origin, point)
            if (math.dist(origin, point) > stats["range"] or
                    not me["stats"].get("min_pitch", -.7) <= aim[1] <= me["stats"].get("max_pitch", 1.3)):
                continue
            if self.world.line_clear(origin, point):
                return ExposedSolution(aim, point, radius, height, predicted, velocity, flight)
        return None

    def _exposed_boresight(self, me, weapon, solved, aim, deadline):
        """Validate the actual barrel ray, not a box around an exposed sample."""
        if time.perf_counter() >= deadline:
            return False
        origin = [*me["pos"][:2], me["pos"][2]+me["stats"].get("muzzle_height", 7)]
        direction = (math.cos(aim[1])*math.cos(aim[0]),
                     math.cos(aim[1])*math.sin(aim[0]), math.sin(aim[1]))
        offset = me["stats"]["radius"]+.5
        barrel = [origin[i]+direction[i]*offset for i in range(3)]
        center = list(solved.center)
        if weapon["kind"] == "gun":
            # A leading ray and an edge of the future body are not enough:
            # the bullet starts radius+.5 ahead and meets a moving body sooner.
            # Solve horizontal relative motion continuously from that barrel.
            speed = weapon["stats"]["speed"]
            center[0] -= solved.velocity[0]*solved.flight
            center[1] -= solved.velocity[1]*solved.flight
            relative = (direction[0]*speed-solved.velocity[0],
                        direction[1]*speed-solved.velocity[1], direction[2]*speed)
            entry = cylinder_entry(barrel, relative, center, solved[2]*.94,
                                   solved[3], weapon["stats"]["range"]/speed)
        else:
            speed = 1
            entry = cylinder_entry(barrel, direction, center, solved[2]*.94,
                                   solved[3], weapon["stats"]["range"])
        if entry is None:
            return False
        point = [barrel[i]+direction[i]*speed*entry for i in range(3)]
        # Starting at the muzzle center also checks the radius+.5 barrel
        # extension: a wall between center and barrel cannot be skipped.
        return self.world.line_clear(origin, point)

    def _solve(self, me, target, weapon, deadline):
        origin = list(me["pos"])
        origin[2] += me["stats"].get("muzzle_height", 7)
        point, radius, height = target_center(target, self.config)
        stats = weapon["stats"]
        kind = weapon["kind"]
        velocity = target.get("vel", [0,0,0])
        if kind == "gun":
            t = intercept(origin, point, velocity, stats["speed"])
            point = [point[i]+velocity[i]*t for i in range(3)]
            # Falling targets accelerate; avoid extrapolating a fall through ground.
            if abs(velocity[2]) > 0.5:
                point[2] -= self.config["mech"]["gravity"]*t*t/2
                point[2] = max(point[2], self.world.ground(*point[:2])+height/2)
            if math.dist(origin, point) > stats["range"]:
                return None
        elif kind == "mortar":
            # Low-angle ballistic solution, iterated with horizontal target motion.
            origin[2] = me["pos"][2]+me["stats"].get("height", 9)+0.5
            speed, gravity = stats["speed"], stats["gravity"]
            base = list(point)
            flight = distance(origin, point)/speed
            for _ in range(5):
                point = [base[i]+velocity[i]*flight for i in range(3)]
                d, dz = distance(origin, point), point[2]-origin[2]
                disc = speed**4-gravity*(gravity*d*d+2*dz*speed*speed)
                if disc < 0 or d < stats.get("splash_radius", 7)+9:
                    return None
                pitch = math.atan2(speed*speed-math.sqrt(disc), gravity*d)
                flight = max(0, (d-3)/max(1, speed*math.cos(pitch)))
            aim = [math.atan2(point[1]-origin[1], point[0]-origin[0]), pitch]
            # Check the arc instead of rejecting targets behind low cover.
            previous = origin
            steps = max(4, math.ceil(flight/0.10))
            for j in range(1, steps+1):
                t = flight*j/steps
                p = [origin[0]+speed*math.cos(pitch)*math.cos(aim[0])*t,
                     origin[1]+speed*math.cos(pitch)*math.sin(aim[0])*t,
                     origin[2]+speed*math.sin(pitch)*t-gravity*t*t/2]
                if not self.world.line_clear(previous, p):
                    return None
                previous = p
            return aim, point, radius, height
        elif math.dist(origin, point) > stats["range"]:
            return None
        if not self.world.line_clear(origin, point):
            if kind in ("gun", "laser"):
                return self._exposed(me, target, weapon, origin, radius, height, deadline)
            return None
        return aim_at(origin, point), point, radius, height

    def action(self, me, targets, retreat, final_duel, return_fire=False, forced_weapon=None):
        if not targets:
            return None, [False, False], None
        options = []
        exposed_deadline = time.perf_counter()+self.EXPOSED_SECONDS
        for target in targets[:8]:
            d = distance(me["pos"], target["pos"])
            hostile = target.get("kind") == "mech"
            gun_only = False
            if retreat and not final_duel and (not hostile or d > 28) and target.get("hp", 1400) > 130:
                if not (return_fire and hostile):
                    continue
                gun_only = True
            for slot, weapon in enumerate(me["weapons"]):
                if weapon is None or (forced_weapon and weapon["kind"] != forced_weapon):
                    continue
                if gun_only and weapon["kind"] != "gun":
                    continue
                solution = self._solve(me, target, weapon, exposed_deadline)
                if solution is None:
                    continue
                aim, point, radius, height = solution
                kind, stats = weapon["kind"], weapon["stats"]
                # Keep tracking between gun shots. Dropping the target during a
                # 0.24 s cooldown used to reset aim and trigger early reloads.
                if kind == "lightning" and me["energy"] < stats.get("energy", 3)+8:
                    continue
                if kind == "laser" and retreat and d < 65 and not weapon.get("charge", 0):
                    continue
                score = (150 if hostile else 0) + 80/(1+d/45)
                score += 55*(1-target.get("hp", 1400)/target.get("max_hp", 1400)) if hostile else 0
                score += {"gun": 15, "laser": 42, "lightning": 60, "mortar": 25}[kind]
                score += 120 if weapon.get("charge", 0) else 0
                score += 24 if target.get("id") == self.locked_id else 0
                score -= weapon.get("cooldown", 0)*65
                if kind == "gun" and (weapon.get("reload", 0) > 0 or weapon.get("ammo", 1) <= 0):
                    score -= 65
                options.append((score, slot, target, solution, gun_only))
        if not options:
            return None, [False, False], None
        _, primary, target, solution, gun_only = max(options, key=lambda o: o[0])
        self.locked_id = target.get("id")
        aim, point, radius, height = solution
        stats_me = me["stats"]
        aim[1] = max(stats_me.get("min_pitch", -0.7), min(stats_me.get("max_pitch", 1.3), aim[1]))
        fire = [False, False]
        for slot, weapon in enumerate(me["weapons"]):
            if not weapon or (forced_weapon and weapon["kind"] != forced_weapon):
                continue
            if gun_only and weapon["kind"] != "gun":
                continue
            solved = solution if slot == primary else self._solve(me, target, weapon, exposed_deadline)
            if solved is None:
                # Keep a charged laser held until the shared aim is useful.
                fire[slot] = bool(weapon.get("charge", 0))
                continue
            desired, p, r, h = solved
            d = max(1, distance(me["pos"], p))
            yaw_error = abs(angle_error(desired[0], me["aim"][0]))
            pitch_error = abs(desired[1]-me["aim"][1])
            # Conservative: fire only when the current actual aim can hit.
            aligned = yaw_error < math.atan2(r+0.3, d) and pitch_error < math.atan2(h*0.44, d)
            kind, stats = weapon["kind"], weapon["stats"]
            if isinstance(solved, ExposedSolution):
                aligned = (self._exposed_boresight(me, weapon, solved, me["aim"], exposed_deadline) and
                           self._exposed_boresight(me, weapon, solved, aim, exposed_deadline))
            if kind == "gun":
                fire[slot] = aligned and weapon.get("ammo", 0) > 0 and weapon.get("reload", 0) <= 0
            elif kind == "lightning":
                fire[slot] = (yaw_error < math.radians(stats["cone_deg"])*0.45 and
                              me["energy"] > stats["energy"]+8)
            elif kind == "laser":
                charge = weapon.get("charge", 0)
                same_aim = abs(angle_error(desired[0], aim[0])) < 0.03 and abs(desired[1]-aim[1]) < 0.03
                if charge > 0:
                    fire[slot] = not (charge >= stats["charge"] and aligned and same_aim)
                else:
                    fire[slot] = same_aim and (not retreat or d > 65)
            elif slot == primary:
                fire[slot] = yaw_error < 0.035 and pitch_error < 0.025
        return aim, fire, target
