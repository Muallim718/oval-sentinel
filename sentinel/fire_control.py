"""Schedule two weapons against one visible mech using its actual hit volume."""
import math

from .combat import Combat, aim_at, target_center
from .geometry import angle_error, distance


STEP = .05
WINDOW = 2 * STEP


def muzzle(me, after):
    return (
        me["pos"][0] + me["vel"][0] * after,
        me["pos"][1] + me["vel"][1] * after,
        me["pos"][2] + me["vel"][2] * after + me["stats"]["muzzle_height"],
    )


def shot_direction(aim):
    yaw, pitch = aim
    return math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)


def intercept_with_barrel(origin, point, velocity, speed, barrel):
    """Flight starts at the tip, so |point + velocity*t - origin| = barrel + speed*t."""
    relative = tuple(b - a for a, b in zip(origin, point))
    a = speed * speed - sum(v * v for v in velocity)
    b = speed * barrel - sum(r * v for r, v in zip(relative, velocity))
    c = sum(r * r for r in relative) - barrel * barrel
    if a <= 0 or c <= 0:
        return 0.0
    return c / (math.sqrt(b * b + a * c) + b)


def body_entry(origin, velocity, center, radius, height, limit):
    """Intersect a swept point against a vertical cylinder in relative coordinates."""
    x, y, z = (a - b for a, b in zip(origin, center))
    vx, vy, vz = velocity
    a = vx * vx + vy * vy
    c = x * x + y * y - radius * radius
    low, high = 0.0, limit
    if a > 1e-9:
        b = vx * x + vy * y
        discriminant = b * b - a * c
        if discriminant < 0:
            return None
        root = math.sqrt(discriminant)
        low, high = max(low, (-b - root) / a), min(high, (-b + root) / a)
    elif c > 0:
        return None
    half_height = height * .5 - .12
    if abs(vz) > 1e-9:
        bottom, top = (-half_height - z) / vz, (half_height - z) / vz
        low, high = max(low, min(bottom, top)), min(high, max(bottom, top))
    elif abs(z) > half_height:
        return None
    return low if low <= high else None


def slew(me, command, after):
    yaw, pitch = me["aim"]
    yaw_step = me["stats"]["turn_rate"] * after
    pitch_step = me["stats"]["pitch_rate"] * after
    return (
        yaw + max(-yaw_step, min(yaw_step, angle_error(command[0], yaw))),
        pitch + max(-pitch_step, min(pitch_step, command[1] - pitch)),
    )


def eligible_phase(weapon):
    delay = weapon.get("cooldown", 0)
    if delay > WINDOW + 1e-7:
        return None
    return STEP if delay <= STEP + 1e-7 else WINDOW


class FireControl(Combat):
    """Keep farming and mortar behavior on the existing planner."""

    def actual_ray(self, me, center, radius, height, velocity, weapon, actual, after):
        kind = weapon["kind"]
        origin = muzzle(me, after)
        barrel = me["stats"]["radius"] + .5
        direction = shot_direction(actual)
        start = tuple(a + barrel * v for a, v in zip(origin, direction))
        center = tuple(a + b * after for a, b in zip(center, velocity))
        speed = weapon["stats"]["speed"] if kind == "gun" else 1.
        target_motion = velocity if kind == "gun" else (0., 0., 0.)
        relative = tuple(speed * v - w for v, w in zip(direction, target_motion))
        hit = body_entry(start, relative, center, .95 * radius, height, weapon["stats"]["range"] / speed)
        if hit is None:
            return False
        end = tuple(a + v * speed * hit for a, v in zip(start, direction))
        return self.world.line_clear(origin, end)

    def direct_aim(self, me, center, radius, height, velocity, weapon, after):
        origin = muzzle(me, after)
        stats, kind = weapon["stats"], weapon["kind"]
        delta = tuple(a - b for a, b in zip(center, origin))
        gap = math.hypot(*delta[:2])
        barrel = me["stats"]["radius"] + .5
        if math.sqrt(sum(d * d for d in delta)) > stats["range"] + barrel + 2:
            return None
        side = (-delta[1] / max(gap, .01), delta[0] / max(gap, .01))
        for shift, lift in ((0., 0.), (0., .37), (.65, .08), (-.65, .08)):
            point = (
                center[0] + velocity[0] * after + side[0] * shift * radius,
                center[1] + velocity[1] * after + side[1] * shift * radius,
                center[2] + velocity[2] * after + lift * height,
            )
            if kind == "gun":
                flight = intercept_with_barrel(origin, point, velocity, stats["speed"], barrel)
                point = tuple(a + v * flight for a, v in zip(point, velocity))
            aim = aim_at(origin, point)
            if not me["stats"]["min_pitch"] <= aim[1] <= me["stats"]["max_pitch"]:
                continue
            if self.actual_ray(me, center, radius, height, velocity, weapon, aim, after):
                return aim
        return None

    def focus(self, me, target, slots, boost, defending):
        center, radius, height = target_center(target, self.config)
        velocity = target.get("vel", (0., 0., 0.))
        d = distance(me["pos"], target["pos"])
        plans = {}
        for slot, weapon in slots:
            kind, stats = weapon["kind"], weapon["stats"]
            phase = eligible_phase(weapon)
            if kind == "gun":
                if weapon.get("reload", 0) > 0 or weapon.get("ammo", 0) <= 0:
                    phase = None
                aim = self.direct_aim(me, center, radius, height, velocity, weapon, phase or STEP)
            elif kind == "laser":
                aim = self.direct_aim(me, center, radius, height, velocity, weapon, STEP)
            else:
                if (d > stats["range"] + .8 or me["energy"] < stats["energy"] + 8 or
                        not self.world.line_clear(muzzle(me, STEP), center)):
                    continue
                aim = aim_at(muzzle(me, STEP), center)
            if aim is not None:
                plans[kind] = (slot, weapon, aim, phase)
        if not plans:
            return None

        gun, laser, arc = (plans.get(kind) for kind in ("gun", "laser", "lightning"))
        if gun and laser and abs(angle_error(gun[2][0], laser[2][0])) < .09:
            # If both barrels fit the same body, keep both clocks ticking.
            shared = [laser[2][0] + .5 * angle_error(gun[2][0], laser[2][0]),
                      .5 * (gun[2][1] + laser[2][1])]
        else:
            shared = None
        choices = [plan[2] for plan in (gun, laser, arc) if plan]
        if shared:
            choices.append(shared)

        charged = next((weapon for _, weapon in slots
                        if weapon["kind"] == "laser" and weapon.get("charge", 0)), None)
        fire_candidates = []
        for command in choices:
            fire = [bool(weapon and weapon["kind"] == "laser" and weapon.get("charge", 0))
                    for weapon in me["weapons"]]
            value = -.4 * abs(angle_error(command[0], me["aim"][0]))
            for kind, (slot, weapon, aim, phase) in plans.items():
                stats = weapon["stats"]
                after = phase or STEP
                actual = slew(me, command, after)
                angular_gap = abs(angle_error(aim[0], command[0]))
                if kind == "gun":
                    valid = self.actual_ray(me, center, radius, height, velocity, weapon, actual, after)
                    fire[slot] = bool(valid and phase is not None)
                    value += stats["damage"] if fire[slot] else 0
                    value += 5 * max(0, 1 - angular_gap / .08)
                elif kind == "lightning":
                    cone = math.radians(stats["cone_deg"]) * .44
                    origin = muzzle(me, after)
                    point = tuple(pos + speed * after for pos, speed in zip(center, velocity))
                    bearing = aim_at(origin, point)[0]
                    fire[slot] = bool(phase and abs(angle_error(bearing, actual[0])) < cone and
                                      distance(origin, point) < stats["range"] and
                                      self.world.line_clear(origin, point))
                    value += (stats["damage"] + (26 if target.get("charging") else 0)) if fire[slot] else 0
                    value += 3 * max(0, 1 - angular_gap / cone)
                else:
                    charge = weapon.get("charge", 0)
                    minimum, full = stats["min_charge"], stats["charge"]
                    damage = stats["damage"] * (stats["min_frac"] +
                                                (1 - stats["min_frac"]) * min(1., charge / full))
                    if "mortar" in target.get("weapons", ()):
                        damage *= 1 + stats.get("cookoff", 0)
                    # End a costly slow-down early for an assured finish or
                    # to resume a sprint, but keep full damage in stable lanes.
                    hp = target.get("hp", target.get("max_hp", math.inf))
                    release = (charge + 1e-7 >= full or hp <= damage * .95 or
                               ((boost or defending) and charge >= max(.35, minimum)))
                    if charge > 0:
                        lined = self.actual_ray(me, center, radius, height, velocity, weapon, actual, STEP)
                        fire[slot] = not (charge + 1e-7 >= minimum and release and lined)
                        value += damage if not fire[slot] else 0
                        if release:
                            value += 10 * max(0, 1 - angular_gap / .05)
                    else:
                        fire[slot] = bool(phase and not boost and not defending and
                                          ("lightning" not in target.get("weapons", ()) or d >= 49) and
                                          (not arc or d > arc[1]["stats"]["range"] + 1) and
                                          abs(angle_error(aim[0], actual[0])) < .23)
                        value += 12 if fire[slot] else 0
                        if not gun or not gun[3]:
                            value += 2 * max(0, 1 - angular_gap / .10)
            # Preserve a hidden charge briefly while tracking with the gun.
            # The game releases it on its own at the published hold limit.
            if charged and not laser and boost:
                fire[next(i for i, w in slots if w is charged)] = False
            fire_candidates.append((value, command, fire))
        _, aim, fire = max(fire_candidates, key=lambda entry: entry[0])
        return list(aim), fire

    def action(self, me, targets, retreat, final_duel, return_fire=False, forced_weapon=None,
               *, boost=False):
        weapons = list((i, w) for i, w in enumerate(me["weapons"]) if w)
        defending = retreat and not final_duel
        if (forced_weapon is not None or any(w["kind"] == "mortar" for _, w in weapons)
                or not me.get("grounded", True) or (defending and not return_fire)):
            return super().action(me, targets, retreat, final_duel, return_fire, forced_weapon)
        hostiles = [e for e in targets[:8] if e.get("kind") == "mech"]
        hostiles.sort(key=lambda e: distance(me["pos"], e["pos"])
                      + e.get("hp", 1400) * .03
                      - (25 if e["id"] == self.locked_id else 0))
        for target in hostiles[:3]:
            if abs(target.get("vel", (0., 0., 0.))[2]) > 1.2:
                # The existing gun solver accounts for gravity during flights.
                continue
            decision = self.focus(me, target, weapons, boost, defending)
            if decision is not None:
                self.locked_id = target["id"]
                return *decision, target
        return super().action(me, targets, retreat, final_duel, return_fire, forced_weapon)
