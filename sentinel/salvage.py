"""Convert a verified kill into real cube rewards when the pickup race is viable.

No loot is invented from a kill event. A short-lived death beacon only associates
observed/remembered cube IDs with the recent fight. Damage estimates are bounded
and conservative; they do not replace the movement controller's collision dodge.
"""
import math
import time
import copy
from .geometry import angle_error, distance, segment_distance_sq, unit
from .cover import firing_lane
from . import tuning


class KillSalvage:
    RESERVE_ENERGY = 30.0
    MAX_SECONDS = 7.0
    MAX_DISTANCE = 120.0
    BEACON_SECONDS = 8.0
    SEARCH_SECONDS = .004

    def __init__(self, world, config, navigator=None):
        self.world, self.config = world, config
        self.navigator = navigator
        self.waypoint = None
        self.routed = False
        self._route_key = None
        self._route_nav = None
        self._route_points = None
        self.beacons = []
        self.cube_seen = {}
        self.goal = None
        self.state = "idle"
        self.sprint = False
        self.reason = "no recent verified kill"
        self.risk = {}
        self.active_cube = None
        self.enemy_speed = config["mech"]["boost_speed"]
        for upgrade in config.get("upgrades", []):
            for effect in upgrade.get("effects", []):
                if effect.get("path") == "mech.boost_speed":
                    self.enemy_speed *= effect.get("mul", 1)**upgrade.get("max", 1)

    @property
    def active(self):
        return self.goal is not None

    def record_kill(self, now, victim, last_seen=None):
        if isinstance(last_seen, tuple):
            seen_at, enemy = last_seen
        elif isinstance(victim, dict):
            seen_at, enemy = (now if last_seen is None else last_seen), victim
        else:
            return
        if now-seen_at > 1 or enemy.get("kind", "mech") != "mech":
            return
        ident = enemy.get("id", victim if isinstance(victim, int) else None)
        self.beacons = [b for b in self.beacons if b["id"] != ident]
        self.beacons.append({"id": ident, "pos": tuple(enemy["pos"]), "t": now})
        self.beacons = self.beacons[-4:]

    def _reject(self, reason):
        self.goal, self.sprint, self.state = None, False, "idle"
        self.waypoint, self.routed = None, False
        self.active_cube = None
        self.reason = reason
        return None

    def _growth(self, me, count):
        size = self.config["cubes"].get("size_per_cube", .05)
        ratio = (1+size*(me["cubes"]+count))/(1+size*me["cubes"])
        return me["stats"]["radius"]*ratio, me["stats"]["height"]*ratio

    def _detour(self, me, cube, cubes, circle, deadline):
        """Return a complete grown-body route; partial A* never owns motion.

        The live Navigator's immutable grid is shared. Its search, links and
        grown-body clearance are private to this short mission. Every locally
        known cube is included in the planning body, even if not on the route;
        actual route intersections determine the reported growth/damage body.
        """
        if self.navigator is None:
            return None
        pickup = self.config["cubes"]["pickup_radius"]
        known = [c for c in cubes if distance(me["pos"], c["pos"]) <= self.MAX_DISTANCE+pickup and
                 abs(c["pos"][2]-self.world.ground(*c["pos"][:2])) < 4]
        radius, height = self._growth(me, len(known))
        stats = me["stats"]
        if not self.world.body_clear(*me["pos"],radius+.2,height,stats["step_up"]):
            self.reason = "post-pickup body has no safe return anchor"
            return None
        goal = (*cube["pos"][:2], self.world.ground(*cube["pos"][:2]))
        # An exact anchor stays within pickup range even with ordinary gait's
        # arrival/braking band. Never substitute a merely nearby grid cell.
        anchors = [goal]
        for i in range(8):
            x, y = goal[0]+.75*math.cos(i*math.pi/4), goal[1]+.75*math.sin(i*math.pi/4)
            anchors.append((x, y, self.world.ground(x, y)))
        anchor = None
        for point in anchors:
            if time.perf_counter() >= deadline:
                self.reason = "salvage route budget exhausted"
                return None
            if (math.dist(point,cube["pos"]) < max(.1,pickup-2.4) and
                    self.world.body_clear(*point,radius+.2,height,stats["step_up"])):
                anchor = point
                break
        if anchor is None:
            self.reason = "no growth-safe exact pickup anchor"
            return None
        key = (tuple(anchor),round(radius,3),round(height,3))
        if key != self._route_key:
            nav = copy.copy(self.navigator)
            nav.links, nav.clearance, nav.path = {}, {}, []
            nav.goal, nav.search, nav.search_done = None, None, True
            nav.radius, nav.height, nav.step_up = radius+.2, height, stats["step_up"]
            nav.body_changed = True
            self._route_key, self._route_nav, self._route_points = key, nav, None
        if self._route_points is None:
            # Existing A* has a hard expansion cap and <=9ms search slice.
            # A slice exceeding our remaining evaluation budget is retained
            # for the next observation, and cannot authorize movement now.
            if deadline-time.perf_counter() < tuning.PLAN_SECONDS+.001:
                self.reason = "insufficient salvage budget for an A* slice"
                return None
            route = self._route_nav.plan(me["pos"], anchor, circle, [])
            if not self._route_nav.search_done:
                self.reason = "bounded salvage detour search continues"
                return None
            if not route or not self.world.walk_clear(route[-1],anchor,radius+.2,height,
                    stats["step_up"],stats["max_slope_deg"]):
                self.reason = "detour has no exact body-safe pickup connection"
                return None
            self._route_points = list(route)+[anchor]
        points = self._route_points
        closest = min(range(len(points)), key=lambda i:distance(me["pos"],points[i]))
        remaining = points[closest:]
        for i in range(min(5,len(remaining))-1,-1,-1):
            if time.perf_counter() >= deadline:
                self.reason = "salvage route budget exhausted"
                return None
            if self.world.walk_clear(me["pos"],remaining[i],radius+.2,height,
                                     stats["step_up"],stats["max_slope_deg"]):
                remaining = remaining[i:]
                break
        path = [tuple(me["pos"])]+remaining
        if sum(distance(a,b) for a,b in zip(path,path[1:])) > self.MAX_DISTANCE:
            self.reason = "post-pickup body cannot safely traverse or exit this detour"
            return None
        for a,b in zip(path,path[1:]):
            for start,end in ((a,b),(b,a)):
                if time.perf_counter() >= deadline:
                    self.reason = "salvage route budget exhausted"
                    return None
                if not self.world.walk_clear(start,end,radius+.2,height,stats["step_up"],stats["max_slope_deg"]):
                    self.reason = "post-pickup body cannot safely traverse or exit this detour"
                    return None
        if time.perf_counter() >= deadline:
            self.reason = "salvage route budget exhausted"
            return None
        return remaining, anchor, radius, height, len(known)

    def _travel_route(self, me, points, radius, height, deadline):
        """Conservative 20Hz acceleration/energy route check, with real terrain."""
        stats, energy = me["stats"], me["energy"]
        p, path = list(me["pos"]), [tuple(me["pos"])]
        vx, vy = me["vel"][:2]
        remaining = list(points)
        for tick in range(1,141):
            if time.perf_counter() >= deadline:
                return math.inf,path,energy
            # Smooth only across a proved whole-body ground corridor.
            if distance(p,remaining[0]) < 5 and len(remaining)>1:
                for i in range(min(5,len(remaining))-1,0,-1):
                    if time.perf_counter() >= deadline:
                        return math.inf,path,energy
                    if self.world.walk_clear(p,remaining[i],radius+.2,height,stats["step_up"],stats["max_slope_deg"]):
                        remaining = remaining[i:]
                        break
            goal = remaining[0]
            direction = unit(goal[0]-p[0],goal[1]-p[1])
            boost = energy-stats["boost_drain"]*.05 >= self.RESERVE_ENERGY
            speed = stats["boost_speed"] if boost else stats["walk_speed"]
            dx,dy = direction[0]*speed-vx,direction[1]*speed-vy
            fraction = min(1,stats["ground_accel"]*.05/max(1e-9,math.hypot(dx,dy)))
            vx,vy = vx+dx*fraction,vy+dy*fraction
            x,y = p[0]+vx*.05,p[1]+vy*.05
            q = [x,y,self.world.ground(x,y)]
            if not self.world.walk_clear(p,q,radius+.2,height,stats["step_up"],stats["max_slope_deg"]):
                return math.inf,path,energy
            p=q;path.append(tuple(p))
            if boost:energy-=stats["boost_drain"]*.05
            if distance(p,goal)<1.2:
                if len(remaining)==1:
                    return tick*.05+.2,path,energy
                remaining.pop(0)
        return math.inf,path,energy

    def _travel(self, me, goal):
        stats = me["stats"]
        p = list(me["pos"])
        vx, vy = me["vel"][:2]
        energy = me["energy"]
        path = [tuple(p)]
        for tick in range(1, 141):
            direction = unit(goal[0]-p[0], goal[1]-p[1])
            boost = energy-stats["boost_drain"]*.05 >= self.RESERVE_ENERGY
            speed = stats["boost_speed"] if boost else stats["walk_speed"]
            dx, dy = direction[0]*speed-vx, direction[1]*speed-vy
            fraction = min(1, stats["ground_accel"]*.05/max(1e-9, math.hypot(dx, dy)))
            vx, vy = vx+dx*fraction, vy+dy*fraction
            x, y = p[0]+vx*.05, p[1]+vy*.05
            p = [x, y, self.world.ground(x, y)]
            path.append(tuple(p))
            if boost:
                energy -= stats["boost_drain"]*.05
            if distance(p, goal) < 1:
                return tick*.05, path, energy
        return math.inf, path, energy

    def _projectile_damage(self, obs, path, future_radius, future_height, deadline, full_path=False):
        me = obs["self"]
        damage = 0.0
        for projectile in obs["projectiles"]:
            if time.perf_counter() >= deadline:
                return math.inf
            mortar = projectile["kind"] == "mortar"
            stats = self.config["weapons"]["mortar" if mortar else "gun"]
            if projectile["kind"] == "npc":
                shot_damage = self.config["npc"]["damage"]
            else:
                shot_damage = stats["damage"]+(stats.get("splash", 0) if mortar else 0)
            radius = future_radius+(stats.get("splash_radius", 0) if mortar else .4)
            for i in range(1, len(path) if full_path else min(len(path), 26)):
                a, b = (i-1)*.05, i*.05
                pp, velocity = projectile["pos"], projectile["vel"]
                bullet_a = [pp[j]+velocity[j]*a for j in range(3)]
                bullet_b = [pp[j]+velocity[j]*b for j in range(3)]
                if mortar:
                    bullet_a[2] -= stats["gravity"]*a*a/2
                    bullet_b[2] -= stats["gravity"]*b*b/2
                rx, ry = bullet_a[0]-path[i-1][0], bullet_a[1]-path[i-1][1]
                dx = bullet_b[0]-bullet_a[0]-(path[i][0]-path[i-1][0])
                dy = bullet_b[1]-bullet_a[1]-(path[i][1]-path[i-1][1])
                fraction = max(0, min(1, -(rx*dx+ry*dy)/(dx*dx+dy*dy or 1)))
                relative_z = (bullet_a[2]+(bullet_b[2]-bullet_a[2])*fraction-
                              (path[i-1][2]+(path[i][2]-path[i-1][2])*fraction))
                if math.hypot(rx+dx*fraction, ry+dy*fraction) < radius and -.5 < relative_z < future_height+.5:
                    hit = [bullet_a[j]+(bullet_b[j]-bullet_a[j])*fraction for j in range(3)]
                    if mortar or self.world.line_clear(pp, hit):
                        damage += shot_damage*self.config["mech"].get("rear_mult", 1.5)
                        break
        return damage*max(0, 1-me["stats"].get("armor", 0))

    def _future_damage(self, obs, path, eta, enemies, deadline, full_path=False):
        me = obs["self"]
        total = 0.0
        points = path if full_path else [path[round((len(path)-1)*f)] for f in (0, .33, .66, 1)]
        for enemy, confidence in enemies:
            if time.perf_counter() >= deadline:
                return math.inf
            npc = enemy.get("kind") == "npc"
            if full_path:
                visible = False
                for point in points:
                    if time.perf_counter() >= deadline:
                        return math.inf
                    if npc:
                        origin = [*enemy["pos"][:2],enemy["pos"][2]+self.config["npc"]["height"]*.7]
                        seen = self.world.line_clear(origin,[*point[:2],point[2]+me["stats"]["height"]*.5])
                    else:
                        seen = firing_lane(self.world,self.config,point,me,enemy)[0]
                    if seen:
                        visible=True
                        break
            elif npc:
                origin = [*enemy["pos"][:2], enemy["pos"][2]+self.config["npc"]["height"]*.7]
                visible = any(self.world.line_clear(origin, [*point[:2], point[2]+me["stats"]["height"]*.5])
                              for point in points)
            else:
                visible = any(firing_lane(self.world, self.config, point, me, enemy)[0] for point in points)
            if not visible:
                continue
            minimum = min(distance(point, enemy["pos"]) for point in points)
            if npc:
                stats = self.config["npc"]
                first = minimum/stats["projectile_speed"]
                if minimum <= stats["deaggro_range"] and first <= eta:
                    total += (1+math.floor((eta-first)/stats["cooldown"]))*stats["damage"]
                continue
            multiplier = 1+self.config["cubes"].get("damage_per_cube", .04)*min(
                enemy.get("cubes", 0), self.config["cubes"].get("stat_cap", 10))
            bearing = math.atan2(enemy["pos"][1]-me["pos"][1], enemy["pos"][0]-me["pos"][0])
            if abs(angle_error(bearing, me["aim"][0])) > math.pi/2:
                multiplier *= self.config["mech"].get("rear_mult", 1.5)
            for kind in enemy.get("weapons", ["gun"]):
                stats = self.config["weapons"].get(kind)
                if not stats:
                    continue
                if kind == "gun":
                    first = minimum/stats["speed"]
                    if minimum > stats["range"] or first > eta:
                        continue
                    shots = min(stats["mag"], 1+math.floor((eta-first)/stats["cooldown"]))
                    total += shots*stats["damage"]*multiplier
                elif kind == "laser" and minimum <= stats["range"]:
                    first = 0 if enemy.get("charging") else stats["charge"]
                    if first <= eta:
                        shots = 1+math.floor((eta-first)/(stats["cooldown"]+stats["charge"]))
                        cookoff = stats.get("cookoff", .6) if any(w and w["kind"] == "mortar" for w in me["weapons"]) else 0
                        total += shots*stats["damage"]*(1+cookoff)*multiplier
                elif kind == "lightning" and minimum <= stats["range"]+self.enemy_speed*eta:
                    total += (1+math.floor(eta/stats["cooldown"]))*stats["damage"]*multiplier
                elif kind == "mortar":
                    first = minimum/stats["speed"]
                    if first <= eta:
                        total += (stats["damage"]+stats["splash"])*multiplier
        return total*max(0, 1-me["stats"].get("armor", 0))

    def choose(self, obs, cubes, threats, circle, emergency=False):
        me, now = obs["self"], obs["t"]
        previous = self.active_cube
        self.goal, self.sprint, self.state = None, False, "idle"
        self.waypoint, self.routed = None, False
        self.risk = {}
        self.beacons = [beacon for beacon in self.beacons if now-beacon["t"] < self.BEACON_SECONDS]
        for cube in obs["cubes"]:
            self.cube_seen[cube["id"]] = now
        self.cube_seen = {ident: stamp for ident, stamp in self.cube_seen.items() if now-stamp < 25}
        if emergency or not me["in_zone"] or not me["grounded"]:
            return self._reject("emergency overrides salvage")
        if any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"]):
            return self._reject("release existing laser charge before a salvage dash")
        if not self.beacons:
            return self._reject("no recent verified kill")
        if len(obs["projectiles"]) > 32:
            return self._reject("incoming volley overload")
        cubes = list(cubes)
        dead = {beacon["id"] for beacon in self.beacons}
        enemies = [(enemy, confidence) for enemy, confidence in threats
                   if enemy.get("kind") == "mech" and enemy.get("id") not in dead and confidence >= .25]
        eligible = []
        visible_ids = {item["id"] for item in obs["cubes"]}
        for cube in cubes:
            if distance(me["pos"], cube["pos"]) > self.MAX_DISTANCE:
                continue
            if abs(cube["pos"][2]-self.world.ground(*cube["pos"][:2])) >= 4:
                continue
            if cube["id"] not in visible_ids and distance(me["pos"], cube["pos"]) < 7:
                eye = [*me["pos"][:2], me["pos"][2]+me["stats"]["eye_height"]]
                if abs(me["pos"][2]-cube["pos"][2]) < 4 and self.world.line_clear(
                        eye, [*cube["pos"][:2], cube["pos"][2]+1]):
                    continue  # A nearby explicit negative observation beats stale memory.
            if any(distance(cube["pos"], b["pos"]) <= 12 and
                   self.cube_seen.get(cube["id"], -100) >= b["t"]-.5 for b in self.beacons):
                eligible.append(cube)
        eligible.sort(key=lambda cube: (cube["id"] != previous, distance(me["pos"], cube["pos"])))
        if not eligible:
            return self._reject("no known available cube near the verified kill")
        started = time.perf_counter()
        deadline = started+self.SEARCH_SECONDS
        # Spend detour time on a substantial confirmed bundle. Four compact
        # cubes can materially change the next fight and deny the same power
        # to a pursuer. Every original direct candidate still comes first.
        attempts = [(cube, False) for cube in eligible[:6]]
        pickup = self.config["cubes"]["pickup_radius"]
        if len(eligible) >= 4:
            for cube in eligible[:6]:
                bundle = sum(distance(cube["pos"], other["pos"]) <= pickup * .75
                             for other in eligible)
                if bundle >= 4:
                    attempts.append((cube, True))
                    break
        blocked_goals = set()
        for cube,allow_route in attempts:
            if allow_route:
                deadline = started+self.SEARCH_SECONDS+.010
            if time.perf_counter() >= deadline:
                return self._reject("salvage route budget exhausted")
            goal = tuple(cube["pos"][:2])
            if goal in blocked_goals and not allow_route:
                continue
            margin = min(12, max(4, circle[1]*.1))
            if distance(goal, circle[0]) >= circle[1]-margin:
                self.reason = "kill reward is outside the predicted safe zone"
                continue
            stats = me["stats"]
            ground_goal = (*goal, self.world.ground(*goal))
            pickup = self.config["cubes"]["pickup_radius"]
            possible = [item for item in cubes if segment_distance_sq(
                item["pos"][0], item["pos"][1], me["pos"], goal) <= pickup*pickup and
                abs(item["pos"][2]-self.world.ground(*item["pos"][:2])) < 4]
            future_radius, future_height = self._growth(me,len(possible))
            routed = False
            waypoint = None
            direct = goal not in blocked_goals and self.world.walk_clear(
                me["pos"], ground_goal, future_radius+.2, future_height, stats["step_up"], stats["max_slope_deg"])
            if allow_route and direct:
                continue  # Every direct candidate was already evaluated first.
            if not direct:
                self.reason = "post-pickup body cannot safely traverse or exit this corridor"
                if not allow_route:
                    blocked_goals.add(goal)
                    continue
                detour = self._detour(me,cube,cubes,circle,deadline)
                if detour is None:
                    # Preserve one bounded A* search across observations,
                    # rather than restart for every cube in the same bundle.
                    if "search continues" in self.reason or "budget" in self.reason:
                        return self._reject(self.reason)
                    continue
                points, ground_goal, future_radius, future_height, growth_bound = detour
                possible = [item for item in cubes if any(segment_distance_sq(
                    item["pos"][0],item["pos"][1],a,b)<=pickup*pickup
                    for a,b in zip([me["pos"]]+points,points)) and
                    abs(item["pos"][2]-self.world.ground(*item["pos"][:2]))<4]
                # Keep the conservative all-local-known growth body for the
                # rollout too: acceleration/gait may collect a cube beside a
                # nominal straight segment before reaching the reward.
                eta,path,energy_left = self._travel_route(me,points,future_radius,future_height,deadline)
                if time.perf_counter() >= deadline:
                    return self._reject("salvage route budget exhausted")
                routed,waypoint,goal = True,points[0],tuple(ground_goal[:2])
            else:
                eta, path, energy_left = self._travel(me, goal)
            if eta > self.MAX_SECONDS:
                self.reason = "kill reward cannot be reached before the short window closes"
                continue
            if routed and any(distance(point,circle[0]) >= circle[1]-margin for point in path):
                self.reason = "salvage detour leaves the predicted safe zone"
                continue
            expiry = max(beacon["t"]+self.BEACON_SECONDS for beacon in self.beacons
                         if distance(cube["pos"], beacon["pos"]) <= 12 and
                         self.cube_seen.get(cube["id"], -100) >= beacon["t"]-.5)
            if now+eta+.25 >= expiry:
                self.reason = "pickup cannot finish before the fresh kill window expires"
                continue
            race = min(((max(0, distance(goal, enemy["pos"])-pickup)/max(
                self.enemy_speed, math.hypot(*enemy.get("vel", [0, 0])[:2])))-eta
                for enemy, _ in enemies), default=math.inf)
            if race <= .20:
                self.reason = "another mech wins the pickup race"
                continue
            tight = [item for item in cubes if distance(item["pos"], goal) <= max(.5, pickup-2.4) and
                     abs(item["pos"][2]-ground_goal[2]) < 4 and now-self.cube_seen.get(item["id"], -100) <= .5]
            capped = min(len(tight), max(0, self.config["cubes"].get("stat_cap", 10)-me["cubes"]))
            base_hp = me["max_hp"]/(1+self.config["cubes"].get("hp_per_cube", .04)*min(
                me["cubes"], self.config["cubes"].get("stat_cap", 10)))
            healing = capped*base_hp*self.config["cubes"].get("hp_per_cube", .04)
            projectile = self._projectile_damage(obs, path, future_radius, future_height, deadline, full_path=routed)
            npcs = [(npc, 1) for npc in obs["mechs"] if npc.get("kind") == "npc"]
            future = self._future_damage(obs, path, eta, enemies+npcs, deadline, full_path=routed)
            remaining = me["hp"]+healing-projectile-future
            self.risk = {"eta": eta, "healing": healing, "projectile_damage": projectile,
                         "future_damage": future, "remaining_hp": remaining,
                         "race_margin": race, "growth_cubes": len(possible),
                         "future_radius": future_radius, "escape_energy": energy_left}
            if routed:
                self.risk["routed"] = True
                self.risk["growth_bound"] = growth_bound
            if time.perf_counter() >= deadline:
                return self._reject("salvage route budget exhausted")
            if remaining < max(250, me["max_hp"]*.25):
                self.reason = "estimated pickup HP is below the next-battle reserve"
                continue
            if routed and projectile+future >= me["hp"]-max(40,me["max_hp"]*.05):
                self.reason = "detour damage can be lethal before pickup healing arrives"
                continue
            self.goal, self.active_cube, self.state = goal, cube["id"], "collect"
            self.waypoint,self.routed = waypoint,routed
            self.sprint = me["energy"] > self.RESERVE_ENERGY+stats["boost_drain"]*.1
            self.reason = "commit to the verified kill reward within HP and arrival budgets"
            return self.goal
        return self._reject(self.reason)
