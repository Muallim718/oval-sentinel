"""Short ground-motion rollouts that keep a chosen shelter instead of orbiting out.

The planner is deliberately small: a fixed set of commands, published acceleration,
body/path checks, and bounded line-of-fire checks. It is not a game simulation.
"""
import math

from .geometry import angle_error, distance, unit
from .cover import firing_lane
from .incoming import STEP, STEPS, impact_cost, incoming_tracks


def forecast_path(me, move, speed):
    """Use the same acceleration samples for collision, travel, and bullet risk."""
    x, y, z = me["pos"]
    vx, vy = me["vel"][:2]
    acceleration = me["stats"]["ground_accel" if me.get("grounded", True) else "air_accel"]
    target_x, target_y = move[0] * speed, move[1] * speed
    path = [(x, y, z)]
    for tick in range(1, 16):
        dx, dy = target_x - vx, target_y - vy
        fraction = min(1, acceleration * STEP / max(1e-9, math.hypot(dx, dy)))
        vx, vy = vx + dx * fraction, vy + dy * fraction
        x, y = x + vx * STEP, y + vy * STEP
        feet = z
        if not me["grounded"]:
            elapsed = tick * STEP
            feet += me["vel"][2] * elapsed - me["stats"]["gravity"] * elapsed**2 / 2
        path.append((x, y, feet))
    return path


def duel_strafe(now, enemy, point):
    """Vary lateral speed faster than the old two-second half-orbit."""
    away = unit(point[0] - enemy["pos"][0], point[1] - enemy["pos"][1])
    # Uneven intervals make a constant-velocity aim estimate less reliable.
    cycle = (now + 0.13 * enemy.get("id", 0)) % 1.91
    direction = 1 if cycle < .43 or .99 <= cycle < 1.57 else -1
    return -away[1] * direction, away[0] * direction


class GroundSteering:
    def __init__(self, world, config):
        self.world, self.config = world, config
        self.blocked = False

    def exposed(self, point, me, enemy):
        ground = max(point[2], self.world.ground(*point[:2]))
        return firing_lane(self.world, self.config, (*point[:2], ground), me, enemy)[0]

    def choose(self, obs, waypoint, threats, mode, fight_range, retreat,
               sprinting=False, cover=False, circle=None):
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        circle = circle or (obs["zone"]["center"], obs["zone"]["radius"])
        # A hidden pursuer must not keep pushing us away through its wall.
        considered = [(e, c) for e, c in threats if distance(p, e["pos"]) < 250][:15]
        lanes = [(e, c, self.exposed(p, me, e)) for e, c in considered]
        lanes.sort(key=lambda ec: (not ec[2], distance(p, ec[0]["pos"])/max(.25, ec[1])))
        nearby = [(e, c) for e, c, seen in lanes[:3]]
        visibility = [seen for e, c, seen in lanes[:3]]
        visible = [(e, c) for (e, c), seen in zip(nearby, visibility) if seen]
        desired = unit(waypoint[0]-p[0], waypoint[1]-p[1])
        if visible and not cover:
            enemy = visible[0][0]
            away = unit(p[0]-enemy["pos"][0], p[1]-enemy["pos"][1])
            preferred = fight_range if mode == "fight" else 90
            force = max(-.7 if mode == "fight" else 0,
                        min(1.4, (preferred-distance(p, enemy["pos"]))/40))
            orbit = math.sin(now*1.7)*.65
            desired = unit(desired[0]+away[0]*force-away[1]*orbit,
                           desired[1]+away[1]*force+away[0]*orbit)
        angle = math.atan2(desired[1], desired[0])
        # Braking is a command, not an assumption that velocity is already zero.
        commands = [(0., 0.)]
        commands += [(math.cos(angle+a), math.sin(angle+a))
                     for a in (0, .40, -.40, .85, -.85, 1.4, -1.4, math.pi)]
        speed = stats["boost_speed"] if sprinting else stats["walk_speed"]
        # Stop sprinting before a shelter; otherwise braking overshoots the edge.
        if cover and distance(p, waypoint) < 12:
            sprinting, speed = False, stats["walk_speed"]
        if any(w and w["kind"] == "laser" and w.get("charge", 0) > 0
               for w in me["weapons"]):
            speed *= stats.get("charge_move_mult", .5)
        tracks = incoming_tracks(obs, self.config, speed)
        splash = self.config["weapons"]["mortar"]["splash_radius"]
        strafe = None
        if mode == "fight" and len(visible) == 1 and not cover and me["grounded"]:
            enemy = visible[0][0]
            separation = distance(p, enemy["pos"])
            if 60 <= separation <= max(155, fight_range + 25) and abs(separation - fight_range) < 30:
                strafe = duel_strafe(now, enemy, p)
                commands += [strafe, (-strafe[0], -strafe[1])]
        follow_terrain = (tracks and me["grounded"] and
                          p[2] <= self.world.ground(*p[:2]) + stats["step_up"])
        best = None
        for command in commands:
            path = forecast_path(me, command, speed)
            q, far = path[8], path[15]
            anchors = (p, path[4], q, path[STEPS]) if tracks else (p, q)
            if not all(self.world.walk_clear(start, end, stats["radius"]+.3, stats["height"],
                                             stats["step_up"], stats["max_slope_deg"])
                       for start, end in zip(anchors, anchors[1:])):
                continue
            score = distance(q, waypoint)*1.0+distance(far, waypoint)*.32
            score += max(0, distance(q, circle[0])-circle[1]+4)*16
            # Body exposure dominates a few meters of route shortening when
            # escaping. At a safe shelter the zero command can actually win.
            for (enemy, confidence), seen_here in zip(nearby, visibility):
                d = distance(q, enemy["pos"])
                seen_next = self.exposed(q, me, enemy)
                if seen_next:
                    score += (34 if cover or retreat else 8)*confidence
                    score += max(0, 70-d)*(1.2 if mode != "fight" else .25)*confidence
                    if not seen_here:
                        score += (22 if cover or retreat else 6)*confidence
                    if enemy.get("charging"):
                        ep = enemy["pos"]
                        bearing = math.atan2(q[1]-ep[1], q[0]-ep[0])
                        score += max(0, 1-abs(angle_error(bearing, enemy["aim"][0]))/.16)*24
                if mode == "fight" and not cover:
                    score += abs(d-fight_range)*.28*confidence
            if tracks:
                if follow_terrain:
                    path[1:STEPS+1] = [(x, y, self.world.ground(x, y))
                                       for x, y, _ in path[1:STEPS+1]]
                score += impact_cost(self.world, me, path, tracks, splash)
            if strafe is not None:
                score -= 5.5 * (command[0] * strafe[0] + command[1] * strafe[1])
            if command == (0., 0.) and distance(p, waypoint) > 5:
                score += 3  # do not stop indefinitely on the way to useful cover
            if command == (0., 0.) and visible and mode == "fight" and not cover:
                score += 8  # preserve evasive motion in an exposed gun duel
            if best is None or score < best[0]:
                best = score, list(command)
        self.blocked = best is None
        return (best[1], sprinting) if best else (list(desired), sprinting)
