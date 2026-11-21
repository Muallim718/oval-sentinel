"""Intercept aiming and trigger discipline. Both slots share one torso aim."""
import math
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


def shot_window(weapon):
    """Bracket a shot in the next two 20 Hz steps, without assuming update order.

    A ready weapon can fire before or after the first movement/torso update. A
    cooldown lasting through that step moves the bracket to the second step.
    Holding the trigger during a longer cooldown is harmless; keep tracking the
    last bracket until a later observation provides its actual ready time.
    """
    end = .05 if weapon.get("cooldown", 0) <= .05+1e-9 else .10
    return end-.05, end


def slew_aim(me, command, seconds):
    """Actual shared torso direction after bounded yaw and pitch movement."""
    stats = me["stats"]
    yaw_change = angle_error(command[0], me["aim"][0])
    yaw_limit = stats.get("turn_rate", 4)*seconds
    pitch_limit = stats.get("pitch_rate", 3)*seconds
    return [me["aim"][0]+max(-yaw_limit, min(yaw_limit, yaw_change)),
            me["aim"][1]+max(-pitch_limit, min(pitch_limit, command[1]-me["aim"][1]))]


def launch_origin(me, seconds, move=None, boost=False):
    """Forecast the muzzle using current inertia and the already-selected move.

    When no command is supplied, use the observed horizontal velocity. This
    keeps Combat useful on its own and avoids inventing a movement intention.
    """
    position = list(me["pos"])
    velocity = list(me.get("vel", [0, 0, 0]))
    stats = me["stats"]
    grounded = me.get("grounded", True)
    command = None
    if move is not None:
        norm = max(1, math.hypot(*move))
        speed = stats["boost_speed"] if boost and grounded else stats["walk_speed"]
        if any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"]):
            speed *= stats.get("charge_move_mult", .5)
        command = [move[0]/norm*speed, move[1]/norm*speed]
    steps = max(1, math.ceil(seconds/.05))
    dt = seconds/steps
    for _ in range(steps):
        if command is not None:
            dx, dy = command[0]-velocity[0], command[1]-velocity[1]
            change = math.hypot(dx, dy)
            acceleration = stats.get("ground_accel" if grounded else "air_accel", 58.5 if grounded else 12)
            fraction = min(1, acceleration*dt/max(1e-9, change))
            velocity[0], velocity[1] = velocity[0]+dx*fraction, velocity[1]+dy*fraction
        if not grounded:
            acceleration_z = (stats.get("jet_accel", 34) if boost else 0)-stats.get("gravity", 22)
            velocity[2] = min(stats.get("max_rise_speed", 10), velocity[2]+acceleration_z*dt)
        for i in range(3):
            position[i] += velocity[i]*dt
    position[2] += stats.get("muzzle_height", 7)
    return position


class Combat:
    def __init__(self, world, config):
        self.world, self.config = world, config
        self.locked_id = None

    def solve(self, me, target, weapon, delay=0, move=None, boost=False, check_world=True):
        origin = launch_origin(me, delay, move, boost)
        point, radius, height = target_center(target, self.config)
        stats = weapon["stats"]
        kind = weapon["kind"]
        velocity = target.get("vel", [0,0,0])
        base = list(point)
        if kind in ("gun", "laser"):
            point = [point[i]+velocity[i]*delay for i in range(3)]
        if kind == "gun":
            t = intercept(origin, point, velocity, stats["speed"])
            total = delay+t
            point = [base[i]+velocity[i]*total for i in range(3)]
            # Falling targets accelerate; avoid extrapolating a fall through ground.
            if abs(velocity[2]) > 0.5:
                point[2] -= self.config["mech"]["gravity"]*total*total/2
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
        if check_world and not self.world.line_clear(origin, point):
            return None
        return aim_at(origin, point), point, radius, height

    def planned_solution(self, me, target, weapon, move, boost):
        """Lead to the end of the shot window, using one wall ray.

        The command is held for two physics steps. Midpoint-only prediction can
        leave the next observed torso behind a fast crossing target forever.
        Leading through the window avoids that feedback lag; both possible
        firing orders are still checked against the actual shared torso below.
        """
        if weapon["kind"] not in ("gun", "laser"):
            return self.solve(me, target, weapon)
        times = shot_window(weapon) if weapon["kind"] == "gun" else (0, .05)
        delay = times[1]
        solution = self.solve(me, target, weapon, delay, move, boost, check_world=False)
        # Preserve a valid near-range-boundary opportunity in the earlier case.
        # The two firing checks below still reject an impossible shot.
        if solution is None:
            return self.solve(me, target, weapon)
        origin = launch_origin(me, delay, move, boost)
        return solution if self.world.line_clear(origin, solution[1]) else None

    def aligned_window(self, me, target, weapon, command, move, boost):
        """Check the shared boresight at both ends of its possible firing window.

        Geometry for the chosen shot was checked by planned_solution. These two
        cheap kinematic checks do not cast additional map rays. Neither update
        order is claimed to be the authoritative server order.
        """
        times = shot_window(weapon) if weapon["kind"] == "gun" else (0, .05)
        feasible = 0
        for delay in times:
            solution = self.solve(me, target, weapon, delay, move, boost, check_world=False)
            if solution is None:
                continue  # A range-edge shot may exist in only one bracket.
            feasible += 1
            desired, point, radius, height = solution
            actual = slew_aim(me, command, delay)
            origin = launch_origin(me, delay, move, boost)
            horizontal = max(1, distance(origin, point))
            if (abs(angle_error(desired[0], actual[0])) >= math.atan2(radius+.3, horizontal) or
                    abs(desired[1]-actual[1]) >= math.atan2(height*.44, horizontal)):
                return False
        return feasible > 0

    def action(self, me, targets, retreat, final_duel, return_fire=False, move=None, boost=False):
        if not targets:
            return None, [False, False], None
        options = []
        for target in targets[:8]:
            d = distance(me["pos"], target["pos"])
            hostile = target.get("kind") == "mech"
            gun_only = False
            if retreat and not final_duel and (not hostile or d > 28) and target.get("hp", 1400) > 130:
                if not (return_fire and hostile):
                    continue
                gun_only = True
            for slot, weapon in enumerate(me["weapons"]):
                if weapon is None:
                    continue
                if gun_only and weapon["kind"] != "gun":
                    continue
                solution = self.planned_solution(me, target, weapon, move, boost)
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
            if not weapon:
                continue
            if gun_only and weapon["kind"] != "gun":
                continue
            solved = solution if slot == primary else self.planned_solution(me, target, weapon, move, boost)
            if solved is None:
                # Keep a charged laser held until the shared aim is useful.
                fire[slot] = bool(weapon.get("charge", 0))
                continue
            desired, p, r, h = solved
            d = max(1, distance(me["pos"], p))
            yaw_error = abs(angle_error(desired[0], me["aim"][0]))
            pitch_error = abs(desired[1]-me["aim"][1])
            # Instant-cone and mortar behavior stays on its existing actual-aim
            # rules. Gun and laser additionally use the shared firing window.
            kind, stats = weapon["kind"], weapon["stats"]
            if kind == "gun":
                fire[slot] = (weapon.get("ammo", 0) > 0 and weapon.get("reload", 0) <= 0 and
                              self.aligned_window(me, target, weapon, aim, move, boost))
            elif kind == "lightning":
                fire[slot] = (yaw_error < math.radians(stats["cone_deg"])*0.45 and
                              me["energy"] > stats["energy"]+8)
            elif kind == "laser":
                charge = weapon.get("charge", 0)
                same_aim = abs(angle_error(desired[0], aim[0])) < 0.03 and abs(desired[1]-aim[1]) < 0.03
                if charge > 0:
                    fire[slot] = not (charge >= stats["charge"] and same_aim and
                                      self.aligned_window(me, target, weapon, aim, move, boost))
                else:
                    fire[slot] = same_aim and (not retreat or d > 65)
            elif slot == primary:
                fire[slot] = yaw_error < 0.035 and pitch_error < 0.025
        return aim, fire, target
