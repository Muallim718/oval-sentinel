"""Short ground-motion rollouts that keep a chosen shelter instead of orbiting out.

The planner is deliberately small: a fixed set of commands, published acceleration,
body/path checks, and bounded line-of-fire checks. It is not a game simulation.
"""
import math

from .geometry import angle_error, distance, unit
from .cover import firing_lane


def forecast(me, move, speed, seconds):
    """Integrate commanded ground velocity with acceleration and existing inertia."""
    x, y, z = me["pos"]
    vx, vy = me["vel"][:2]
    acceleration = me["stats"]["ground_accel" if me.get("grounded", True) else "air_accel"]
    steps = max(1, math.ceil(seconds/.05))
    dt = seconds/steps
    for _ in range(steps):
        dx, dy = move[0]*speed-vx, move[1]*speed-vy
        change = math.hypot(dx, dy)
        fraction = min(1, acceleration*dt/max(1e-9, change))
        vx, vy = vx+dx*fraction, vy+dy*fraction
        x, y = x+vx*dt, y+vy*dt
    return x, y, z


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
        committed_pickup = mode in ("salvage", "opening")
        if visible and not cover and not committed_pickup:
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
        projectiles = sorted(obs["projectiles"], key=lambda pr: distance(p, pr["pos"]))[:10]
        best = None
        for command in commands:
            q = forecast(me, command, speed, .40)
            far = forecast(me, command, speed, .75)
            if not self.world.walk_clear(p, q, stats["radius"]+.3, stats["height"],
                                         stats["step_up"], stats["max_slope_deg"]):
                continue
            score = distance(q, waypoint)*1.0+distance(far, waypoint)*.32
            score += max(0, distance(q, circle[0])-circle[1]+4)*16
            # Body exposure dominates a few meters of route shortening when
            # escaping. At a safe shelter the zero command can actually win.
            for (enemy, confidence), seen_here in zip(nearby, visibility):
                d = distance(q, enemy["pos"])
                seen_next = self.exposed(q, me, enemy)
                if seen_next:
                    recovering_cover = cover or (retreat and not committed_pickup)
                    score += (34 if recovering_cover else 8)*confidence
                    if not committed_pickup:
                        score += max(0, 70-d)*(1.2 if mode != "fight" else .25)*confidence
                    if not seen_here:
                        score += (22 if recovering_cover else 6)*confidence
                    if enemy.get("charging"):
                        ep = enemy["pos"]
                        bearing = math.atan2(q[1]-ep[1], q[0]-ep[0])
                        score += max(0, 1-abs(angle_error(bearing, enemy["aim"][0]))/.16)*24
                if mode == "fight" and not cover:
                    score += abs(d-fight_range)*.28*confidence
            # Closest approach uses our actual rollout velocity, including brake.
            vx, vy = (q[0]-p[0])/.40, (q[1]-p[1])/.40
            for projectile in projectiles:
                pp, velocity = projectile["pos"], projectile["vel"]
                rx, ry = pp[0]-p[0], pp[1]-p[1]
                dx, dy = velocity[0]-vx, velocity[1]-vy
                t = max(0, min(.50, -(rx*dx+ry*dy)/(dx*dx+dy*dy or 1)))
                d = math.hypot(rx+dx*t, ry+dy*t)
                z = pp[2]+velocity[2]*t
                if projectile["kind"] == "mortar":
                    z -= self.config["weapons"]["mortar"]["gravity"]*t*t/2
                if p[2]-2 < z < p[2]+stats["height"]+3:
                    radius = stats["radius"]+(7 if projectile["kind"] == "mortar" else 1)
                    score += max(0, radius+2-d)*12
            if command == (0., 0.) and distance(p, waypoint) > 5:
                score += 3  # do not stop indefinitely on the way to useful cover
            if command == (0., 0.) and visible and mode == "fight" and not cover:
                score += 8  # preserve evasive motion in an exposed gun duel
            if best is None or score < best[0]:
                best = score, list(command)
        self.blocked = best is None
        return (best[1], sprinting) if best else (list(desired), sprinting)
