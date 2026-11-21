"""Ground shelter planning from public wall geometry and observed enemies.

The planner owns a hiding destination, not locomotion or triggers. It never flies
to roofs. Search is bounded and can examine a different wall subset next time.
"""
import math
import time

from .geometry import distance


def firing_lane(world, config, point, me, enemy):
    """Return (exposed, rays_used), including the cylinder's lateral silhouette.

    Center-only rays can call a corner safe while bullets still graze a flank.
    The side samples are perpendicular to the incoming horizontal direction.
    """
    size = 1+config["cubes"].get("size_per_cube", .05)*enemy.get("cubes", 0)
    origin = [*enemy["pos"][:2], enemy["pos"][2]+
              config["mech"].get("muzzle_height", 7)*size]
    dx, dy = point[0]-enemy["pos"][0], point[1]-enemy["pos"][1]
    length = max(1e-9, math.hypot(dx, dy))
    radius = me["stats"]["radius"]*.95
    side_x, side_y = -dy/length*radius, dx/length*radius
    top = point[2]+me["stats"]["height"]*.95
    targets = ((point[0], point[1], point[2]+me["stats"]["height"]*.5),
               (point[0], point[1], top),
               (point[0]+side_x, point[1]+side_y, top),
               (point[0]-side_x, point[1]-side_y, top))
    for rays, target in enumerate(targets, 1):
        if world.line_clear(origin, target):
            return True, rays
    return False, len(targets)


class CoverPlanner:
    CELL = 64.0
    SEARCH_RADIUS = 110.0
    SEARCH_SECONDS = 0.0035
    MAX_ANCHORS = 18
    MAX_THREATS = 4

    def __init__(self, world, config):
        self.world = world
        self.config = config
        self.sites = {}
        # Sample wall sides once. Offset and clearance are computed with live
        # dimensions later, so picking up cubes cannot preserve a narrow refuge.
        for prism in world.prisms:
            for a, b in prism.all_edges:
                dx, dy = b[0]-a[0], b[1]-a[1]
                length = math.hypot(dx, dy)
                if length < 0.1:
                    continue
                count = max(1, math.ceil(length/16.0))
                normal = (-dy/length, dx/length)
                for i in range(count):
                    t = (i+0.5)/count
                    x, y = a[0]+dx*t, a[1]+dy*t
                    key = (math.floor(x/self.CELL), math.floor(y/self.CELL))
                    self.sites.setdefault(key, []).append((x, y, *normal))
        self.goal = None
        self.state = "idle"
        self.sheltered = False
        self.reason = "no active shelter"
        self.evaluations = 0
        self.rays = 0
        self.scan = 0
        self.rejected = []

    def clear(self, reason="no nearby observed enemies"):
        self.goal = None
        self.state = "idle"
        self.sheltered = False
        self.reason = reason

    def reject(self, goal, now, seconds=8):
        """Temporarily avoid a shelter the locomotion layer could not reach."""
        self.rejected.append((tuple(goal[:2]), now+max(0, seconds)))
        if self.goal and distance(goal, self.goal) < 3:
            self.clear("shelter route made no progress")

    def _is_rejected(self, point):
        return any(distance(point, goal) < 3 for goal, _ in self.rejected)

    def _ground_point(self, xy, me, circle):
        radius = me["stats"]["radius"]+0.5
        # Body and a small zone margin must fit, including in tiny late circles.
        margin = min(10.0, max(radius, circle[1]*0.12))
        if circle[1] <= margin or distance(xy, circle[0]) > circle[1]-margin:
            return None
        p = (xy[0], xy[1], self.world.ground(*xy[:2]))
        if not self.world.body_clear(*p, radius, me["stats"]["height"],
                                     me["stats"].get("step_up", 1.2)):
            return None
        return p

    def _visible(self, point, me, enemy):
        visible, rays = firing_lane(self.world, self.config, point, me, enemy)
        self.rays += rays
        return visible

    def _measure(self, point, me, enemies):
        """Weighted firing lanes; protect torso, head, and cylinder flanks."""
        self.evaluations += 1
        exposure = 0.0
        close = 0.0
        all_blocked = True
        for enemy, confidence in enemies:
            d = distance(point, enemy["pos"])
            visible = self._visible(point, me, enemy)
            if visible:
                exposure += confidence*(0.45+max(0, 210-d)/140)
                all_blocked = False
            # A pursuer can round a corner before the five-second healing delay.
            # Prefer protected separation when a near enemy makes us reposition.
            close += confidence*max(0, 60-d)*2.0
        return exposure, close, all_blocked

    def _approach_cost(self, point, me):
        travel = distance(me["pos"], point)
        cost = travel*.30
        if travel > 3 and not self.world.walk_clear(
                me["pos"], point, me["stats"]["radius"]+.3,
                me["stats"]["height"], me["stats"].get("step_up", 1.2),
                me["stats"].get("max_slope_deg", 50)):
            # A* may still reach it, but an unseen building detour should not
            # beat an otherwise equivalent refuge with a clear direct approach.
            cost += 18+min(18, travel*.15)
        return cost

    def _hold(self, me, recovering):
        self.goal = tuple(me["pos"][:2])
        self.state = "holding"
        self.reason = "recover behind solid cover" if recovering else "hold blocked firing lanes"
        return self.goal

    def _anchors(self, me):
        p = me["pos"]
        cell_x, cell_y = math.floor(p[0]/self.CELL), math.floor(p[1]/self.CELL)
        records = []
        for j in range(cell_y-2, cell_y+3):
            for i in range(cell_x-2, cell_x+3):
                for site in self.sites.get((i, j), ()):
                    d = distance(p, site)
                    if d < self.SEARCH_RADIUS:
                        records.append((d, site))
        records.sort(key=lambda record: record[0])
        # Use both sides: prism winding, courtyards, and overhangs need no special
        # interpretation. Body clearance rejects the side inside a solid wall.
        offset = me["stats"]["radius"]+1.8
        points = []
        for _, (x, y, nx, ny) in records[:48]:
            points.append((x+nx*offset, y+ny*offset))
            points.append((x-nx*offset, y-ny*offset))
        return points

    def choose(self, obs, threats, circle, recovering=False):
        """Return a safe ground destination or None; caller decides when to use it.

        threats is [(observed_enemy, confidence), ...], and circle is the already
        predicted (center_xy, radius). Public state says whether to hold or move.
        """
        self.evaluations = self.rays = 0
        me = obs["self"]
        self.rejected = [(point, expiry) for point, expiry in self.rejected if obs["t"] < expiry]
        all_enemies = sorted((ec for ec in threats if ec[0].get("kind") == "mech"
                              and ec[1] >= .25 and distance(me["pos"], ec[0]["pos"]) < 250),
                             key=lambda ec: distance(me["pos"], ec[0]["pos"]))
        enemies = all_enemies[:self.MAX_THREATS]
        extra_enemies = all_enemies[self.MAX_THREATS:]
        if not enemies:
            self.clear()
            return None
        deadline = time.perf_counter()+self.SEARCH_SECONDS
        current = self._ground_point(me["pos"], me, circle)
        current_measure = self._measure(current, me, enemies) if current else None
        # Search is bounded to four threats, but holding must be safe from every
        # relevant observed lane. A fifth exposed enemy vetoes a "safe" hold.
        self.sheltered = bool(current_measure and current_measure[2] and
                              not any(self._visible(current, me, enemy)
                                      for enemy, _ in extra_enemies))
        if self.sheltered:
            # Only a ground refuge can be held. A point under an airborne mech
            # is not the mech's actual sheltered position.
            if me["pos"][2]-current[2] <= me["stats"].get("step_up", 1.2)+0.5:
                if all(distance(me["pos"], enemy["pos"]) >= 35 for enemy, _ in all_enemies):
                    return self._hold(me, recovering)
            else:
                self.sheltered = False

        current_score = (current_measure[0]*100+current_measure[1]
                         if current_measure else math.inf)
        best = None
        previous = self._ground_point(self.goal, me, circle) if self.goal else None
        if previous and not self._is_rejected(previous):
            measure = self._measure(previous, me, enemies)
            travel = distance(me["pos"], previous)
            score = measure[0]*100+measure[1]+self._approach_cost(previous, me)-6
            fully_blocked = measure[2] and not any(
                    self._visible(previous, me, enemy) for enemy, _ in extra_enemies)
            if fully_blocked and travel > 3 and not self.sheltered:
                self.state = "approach"
                self.reason = "keep committed sheltered destination"
                return self.goal
            if not self.sheltered or fully_blocked:
                best = score, previous, measure

        anchors = self._anchors(me)
        examined = 0
        while anchors and examined < min(self.MAX_ANCHORS, len(anchors)):
            if time.perf_counter() >= deadline:
                break
            xy = anchors[(self.scan+examined) % len(anchors)]
            examined += 1
            point = self._ground_point(xy, me, circle)
            if point is None or self._is_rejected(point):
                continue
            measure = self._measure(point, me, enemies)
            if self.sheltered and (not measure[2] or any(
                    self._visible(point, me, enemy) for enemy, _ in extra_enemies)):
                continue
            score = measure[0]*100+measure[1]+self._approach_cost(point, me)
            if best is None or score < best[0]:
                best = score, point, measure
        self.scan = (self.scan+max(1, examined)) % max(1, len(anchors))
        if best and best[0] < current_score-(12 if recovering else 8):
            self.goal = tuple(best[1][:2])
            self.state = "approach"
            self.reason = "move to fewer firing lanes"
            return self.goal
        if self.sheltered:
            # No materially safer protected alternative: keep the actual wall
            # rather than flee into an open firing lane just to gain distance.
            return self._hold(me, recovering)
        self.clear("no safer ground shelter found")
        return None
