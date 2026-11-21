"""Compare evasive commands against observed projectiles on the game clock."""

import math


STEP = 0.05
HORIZON = 0.5
STEPS = round(HORIZON / STEP)


def incoming_tracks(obs, config, speed):
    """Rank rounds by when they can touch the reachable area, not by distance."""
    me = obs["self"]
    x, y, z = me["pos"]
    radius = me["stats"]["radius"]
    splash = config["weapons"]["mortar"]["splash_radius"]
    tracks = []
    for projectile in obs["projectiles"]:
        start, velocity = projectile["pos"], projectile["vel"]
        dx, dy = start[0] - x, start[1] - y
        vx, vy, vz = velocity
        mortar = projectile["kind"] == "mortar"
        reach = radius + 1.25 + (splash if mortar else 0)
        reach += max(speed, math.hypot(*me["vel"][:2])) * HORIZON
        rate = vx * vx + vy * vy
        approach = -(dx * vx + dy * vy)
        offset = dx * dx + dy * dy - reach * reach
        if offset <= 0:
            first = 0.0
        else:
            discriminant = approach * approach - rate * offset
            if rate < 1e-8 or approach <= 0 or discriminant < 0:
                continue
            first = (approach - math.sqrt(discriminant)) / rate
        if first > HORIZON:
            continue
        gravity = config["weapons"]["mortar"]["gravity"] if mortar else 0
        end_z = start[2] + vz * HORIZON - gravity * HORIZON**2 / 2
        peak_z = max(start[2], end_z)
        if gravity and 0 < vz / gravity < HORIZON:
            peak_z = start[2] + vz * vz / (2 * gravity)
        height_allowance = 2 + abs(me["vel"][2]) * HORIZON + (splash if mortar else 0)
        if (peak_z < z - height_allowance or
                min(start[2], end_z) > z + me["stats"]["height"] + height_allowance):
            continue
        tracks.append((first, dx * dx + dy * dy, start, velocity, gravity))
    tracks.sort(key=lambda track: track[:2])
    return [(start, velocity, gravity) for _, _, start, velocity, gravity in tracks[:8]]


def _closest_step(start, end, low, high):
    """Closest horizontal approach while inside the vertical hit interval."""
    dz = end[2] - start[2]
    if abs(dz) < 1e-8:
        if not low <= start[2] <= high:
            return None
        enter, leave = 0.0, 1.0
    else:
        first, last = sorted(((low - start[2]) / dz, (high - start[2]) / dz))
        enter, leave = max(0.0, first), min(1.0, last)
        if enter > leave:
            return None
    dx, dy = end[0] - start[0], end[1] - start[1]
    u = -(start[0] * dx + start[1] * dy) / (dx * dx + dy * dy or 1)
    u = max(enter, min(leave, u))
    return (start[0] + dx * u)**2 + (start[1] + dy * u)**2, u


def impact_cost(world, me, path, tracks, splash):
    """Score the closest unblocked pass for each round through the moving body."""
    radius, height = me["stats"]["radius"], me["stats"]["height"]
    cost = 0.0
    for start, velocity, gravity in tracks:
        # Shells threaten a broader region near an impact. Keep a modest
        # safety envelope because we do not know their exact remaining life.
        footprint = radius + (splash if gravity else 0)
        limit = (footprint + 1.25)**2
        low, high = (-splash, height + splash) if gravity else (-.45, height + .45)
        relative = tuple(start[axis] - path[0][axis] for axis in range(3))
        closest = None
        for index in range(1, STEPS + 1):
            seconds = index * STEP
            x, y, z = path[index]
            point = (start[0] + velocity[0] * seconds,
                     start[1] + velocity[1] * seconds,
                     start[2] + velocity[2] * seconds - gravity * seconds**2 / 2)
            after = (point[0] - x, point[1] - y, point[2] - z)
            approach = _closest_step(relative, after, low, high)
            relative = after
            if approach is None or approach[0] >= limit:
                continue
            if closest is None or approach[0] < closest[0]:
                closest = approach[0], (index - 1 + approach[1]) * STEP
        if closest is None:
            continue
        squared, seconds = closest
        point = (start[0] + velocity[0] * seconds,
                 start[1] + velocity[1] * seconds,
                 start[2] + velocity[2] * seconds - gravity * seconds**2 / 2)
        # An intervening wall reliably kills a straight round. A shell can
        # detonate at a wall, so don't discard its local blast this way.
        if not gravity and not world.line_clear(start, point):
            continue
        clearance = math.sqrt(squared) - footprint
        cost += (18 if gravity else 12) * (1.25 - clearance)
    return cost
