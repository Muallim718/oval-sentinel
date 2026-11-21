"""Proactive roof sanctuary: enter early, land, hold deep, leave before the zone.

Only public solids are used. This is one-roof flight, not a roof-to-roof graph.
"""
import math
import time
from .geometry import distance, segment_distance_sq, unit
from .cover import firing_lane


class RoofSanctuary:
    def __init__(self, world, config):
        self.world, self.config = world, config
        self.sites = self.find_sites(config["mech"])
        self.valid_cache = {(id(site), config["mech"]["radius"], config["mech"]["height"]): True
                            for site in self.sites}
        self.search_offset = 0
        self.site = None
        self.phase = None
        self.reason = "no active roof"
        self.deadline = -1
        self.next_search = 0
        self.last_hit = -100
        self.last_rise = 0
        self.best_height = -math.inf
        self.cross_started = 0
        self.failed = {}
        self.exit_goal = None
        self.exit_entry = None
        self.exit_progress_position = None
        self.exit_progress_at = 0
        self.exit_site = None
        self.failed_exits = {}

    @property
    def active(self):
        return self.site is not None

    def supported(self, prism, xy, radius):
        return prism.contains(*xy[:2]) and all(
            segment_distance_sq(xy[0], xy[1], a, b) >= radius*radius
            for a, b in prism.all_edges)

    def vertical_clear(self, xy, low, high, radius, height):
        steps = max(1, math.ceil(abs(high-low)/1.5))
        return all(self.world.body_clear(xy[0], xy[1], low+(high-low)*i/steps,
                                         radius, height, 0) for i in range(steps+1))

    def roof_path(self, prism, start, end, radius, height):
        steps = max(1, math.ceil(distance(start, end)/1.5))
        for i in range(1, steps+1):
            fraction = i/steps
            x, y = start[0]+(end[0]-start[0])*fraction, start[1]+(end[1]-start[1])*fraction
            if not self.supported(prism, (x, y), radius):
                return False
            if not self.world.body_clear(x, y, prism.top, radius, height, 0):
                return False
        return True

    def find_sites(self, stats):
        sites = []
        radius, height = stats["radius"]+.7, stats["height"]
        for prism in self.world.prisms:
            if getattr(prism, "kind", "building") == "bridge":
                continue
            a, b, c, d = prism.bounds
            cores = [((a+c)/2, (b+d)/2)]
            cores += [(a+(c-a)*x, b+(d-b)*y) for x in (.25, .5, .75) for y in (.25, .5, .75)]
            cores = [xy for xy in cores if self.supported(prism, xy, radius+3) and
                     self.world.body_clear(*xy, prism.top, radius, height, 0)]
            if not cores:
                continue
            cores.sort(key=lambda xy: min(segment_distance_sq(*xy, p, q)
                                          for p, q in prism.all_edges), reverse=True)
            for edge_a, edge_b in sorted(prism.outer, key=lambda edge: distance(*edge), reverse=True)[:3]:
                length = distance(edge_a, edge_b)
                if length < 20:
                    continue
                nx, ny = -(edge_b[1]-edge_a[1])/length, (edge_b[0]-edge_a[0])/length
                for fraction in (.5, .30, .70):
                    mx = edge_a[0]+(edge_b[0]-edge_a[0])*fraction
                    my = edge_a[1]+(edge_b[1]-edge_a[1])*fraction
                    normal_x, normal_y = nx, ny
                    if not prism.contains(mx+normal_x, my+normal_y):
                        normal_x, normal_y = -normal_x, -normal_y
                    launch_xy = (mx-normal_x*(radius+2), my-normal_y*(radius+2))
                    low = self.world.ground(*launch_xy)
                    if not 7 < prism.top-low < 43 or prism.base > low+4:
                        continue
                    entry = (mx+normal_x*(radius+3), my+normal_y*(radius+3), prism.top)
                    if not self.supported(prism, entry, radius):
                        continue
                    hold = next(((*xy, prism.top) for xy in cores
                                 if self.roof_path(prism, entry, xy, radius, height)), None)
                    if hold is None:
                        continue
                    if not self.vertical_clear(launch_xy, low, prism.top+1.5, radius, height):
                        continue
                    if not self.world.walk_clear((*launch_xy, prism.top+1.5),
                                                 (*entry[:2], prism.top+1.5), radius, height, 0):
                        continue
                    sites.append({"launch": (*launch_xy, low), "landing": entry,
                                  "hold": hold, "prism": prism,
                                  "inset": min(math.sqrt(segment_distance_sq(*hold[:2], p, q))
                                               for p, q in prism.all_edges)})
        return sites

    def energy_needed(self, site, me):
        stats = me["stats"]
        rise = site["landing"][2]-site["launch"][2]
        # Cross only to the entry, coast/land, then walk to the deep hold point.
        # Half a second of crossing jet replaces v3's jetting the entire inset.
        return ((rise+1.5)/max(1, stats["max_rise_speed"])+.5)*stats["jet_drain"]+18

    def safe_in_zone(self, site, circle):
        return all(distance(site[key], circle[0]) < circle[1]-12
                   for key in ("launch", "landing", "hold"))

    def valid_site(self, site, me):
        stats = me["stats"]
        key = (id(site), stats["radius"], stats["height"])
        if key in self.valid_cache:
            return self.valid_cache[key]
        radius, height = stats["radius"]+.5, stats["height"]
        launch, entry, hold, prism = site["launch"], site["landing"], site["hold"], site["prism"]
        result = (self.supported(prism, entry, radius) and self.supported(prism, hold, radius+2)
                and self.world.body_clear(*hold, radius, height, 0)
                and self.vertical_clear(launch, launch[2], entry[2]+1.5, radius, height)
                and self.world.walk_clear((*launch[:2], entry[2]+1.5),
                                           (*entry[:2], entry[2]+1.5), radius, height, 0)
                and self.roof_path(prism, entry, hold, radius, height))
        self.valid_cache[key] = result
        return result

    def cancel(self, now, failed=False, reason="roof plan ended"):
        if failed and self.site:
            self.failed[id(self.site)] = now+35
        self.site, self.phase = None, None
        self.reason = reason
        self.next_search = now+8
        self.exit_goal = None
        self.exit_entry = None

    def choose(self, obs, threats, circle):
        me, now = obs["self"], obs["t"]
        deadline = time.perf_counter()+.006
        options = []
        for site in self.sites:
            if self.failed.get(id(site), -1) > now:
                continue
            travel = distance(me["pos"], site["launch"])
            if travel > 60 or not self.safe_in_zone(site, circle):
                continue
            if self.energy_needed(site, me) > me["energy"]:
                continue
            if any(ep["pos"][2] >= site["landing"][2]-6 and distance(ep["pos"], site["hold"]) < 70
                   for ep, _ in threats):
                continue
            # Deep, tall shelter is useful only if the approach is short enough
            # to finish before the known hunter reaches the launch area.
            inset = site["inset"]
            score = travel*.9-self.site_height(site)*.25-inset*.4
            options.append((score, site))
        options.sort(key=lambda pair: pair[0])
        checked = 0
        while options and checked < min(12, len(options)):
            if time.perf_counter() >= deadline:
                break
            site = options[(self.search_offset+checked) % len(options)][1]
            checked += 1
            if self.launch_under_fire(site["launch"], me, threats) or not self.valid_site(site, me):
                continue
            if not self.world.walk_clear(me["pos"], site["launch"], me["stats"]["radius"]+.4,
                                         me["stats"]["height"], me["stats"]["step_up"]):
                continue
            self.search_offset = 0
            return site
        self.search_offset = (self.search_offset+max(1, checked)) % max(1, len(options))
        return None

    def launch_under_fire(self, point, me, threats):
        for enemy, _ in threats:
            kinds = enemy.get("weapons", ["gun"])
            ranges = [self.config["weapons"].get(kind, {}).get("range", 230) for kind in kinds]
            if distance(point, enemy["pos"]) > max(ranges, default=230):
                continue
            if firing_lane(self.world, self.config, point, me, enemy)[0]:
                return True
        return False

    @staticmethod
    def site_height(site):
        return site["landing"][2]-site["launch"][2]

    def _move_to(self, me, goal, gain=.25):
        return [max(-1, min(1, (goal[i]-me["pos"][i])*gain-me["vel"][i]*.12)) for i in range(2)]

    def begin_exit(self, obs, circle, reason):
        self.phase, self.deadline = "exit", obs["t"]+12
        self.reason = reason
        me = obs["self"]
        choices = [site for site in self.sites if site["prism"] is self.site["prism"] and
                   self.failed_exits.get(id(site), -1) <= obs["t"]]
        choices.sort(key=lambda site: distance(site["launch"], circle[0])+
                     distance(me["pos"], site["landing"])*.2)
        deadline = time.perf_counter()+.006
        exit_site = self.site
        for candidate in choices[:6]:
            if time.perf_counter() >= deadline:
                break
            if self.valid_site(candidate, me) and self.roof_path(
                    candidate["prism"], me["pos"], candidate["landing"],
                    me["stats"]["radius"]+.3, me["stats"]["height"]):
                exit_site = candidate
                break
        self.exit_site = exit_site
        self.exit_goal = exit_site["launch"]
        self.exit_entry = exit_site["landing"]
        self.exit_progress_position = tuple(me["pos"])
        self.exit_progress_at = obs["t"]

    def update(self, obs, threats, circle, allow_start=True):
        me, now = obs["self"], obs["t"]
        p, stats = me["pos"], me["stats"]
        weapon_hit = any(event["type"] == "damaged" and
                         event.get("weapon") not in (None, "zone") and
                         event.get("amount", 1) > 0 for event in obs["events"])
        if any(event["type"] == "damaged" for event in obs["events"]):
            self.last_hit = now
        if self.site is None:
            charged = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])
            if (not allow_start or not me["grounded"] or not me["in_zone"] or
                    me["hp"] < me["max_hp"]*.90 or me["energy"] < 85 or
                    now-self.last_hit < 5 or now < self.next_search or charged or
                    any(distance(p, enemy["pos"]) < 180 for enemy, _ in threats) or
                    self.launch_under_fire(p, me, threats)):
                return None
            self.next_search = now+2
            self.site = self.choose(obs, threats, circle)
            if self.site is None:
                return None
            self.phase, self.deadline = "approach", now+12
            self.reason = "healthy early launch before pressure"
        site = self.site
        launch, entry, hold = site["launch"], site["landing"], site["hold"]
        if self.phase == "approach":
            if (not self.safe_in_zone(site, circle) or not self.valid_site(site, me) or
                    now > self.deadline or now-self.last_hit < 5 or
                    me["hp"] < me["max_hp"]*.85 or
                    any(distance(p, enemy["pos"]) < 120 for enemy, _ in threats) or
                    self.launch_under_fire(p, me, threats) or self.launch_under_fire(launch, me, threats)):
                self.cancel(now, True, "launch no longer early and safe")
                return None
            if distance(p, launch) > 5 or not me["grounded"]:
                return {"approach": launch}
            if (distance(p, launch) > 1.3 or math.hypot(*me["vel"][:2]) > 1.3 or
                    not self.vertical_clear(p, p[2], entry[2]+1.5,
                                            stats["radius"]+.4, stats["height"])):
                # GroundSteering intentionally has a broad arrival band. Own the
                # final metres so stopping 2m short cannot prevent takeoff.
                return {"move": self._move_to(me, launch, .35), "boost": False, "jump": False}
            if self.energy_needed(site, me) > me["energy"]:
                self.cancel(now, True, "energy reserve disappeared before launch")
                return None
            self.phase, self.deadline = "ascend", now+8
            self.best_height, self.last_rise = p[2], now
            return {"move": [0, 0], "boost": True, "jump": True}
        if self.phase in ("ascend", "cross"):
            if p[2] > self.best_height+.3:
                self.best_height, self.last_rise = p[2], now
            if me["energy"] < 10 or (self.phase == "ascend" and now-self.last_rise > 1.3):
                self.begin_exit(obs, circle, "flight stalled or emergency reserve reached")
        if self.phase != "exit" and not self.safe_in_zone(site, circle):
            self.begin_exit(obs, circle, "leave early for the next safe circle")
        if self.phase not in ("approach", "exit") and not self.valid_site(site, me):
            self.begin_exit(obs, circle, "changed body invalidated the flight or roof corridor")
        if self.phase in ("settle", "hold") and any(
                enemy["pos"][2] >= entry[2]-5 and distance(p, enemy["pos"]) < 65
                for enemy, _ in threats):
            self.begin_exit(obs, circle, "roof occupied by an elevated enemy")
        if self.phase == "hold":
            charging_lane = any(enemy.get("kind") == "mech" and enemy.get("charging") and
                                distance(p, enemy["pos"]) <= self.config["weapons"]["laser"]["range"] and
                                firing_lane(self.world, self.config, p, me, enemy)[0]
                                for enemy in obs["mechs"])
            if weapon_hit or charging_lane:
                self.begin_exit(obs, circle, "leave a roof under actual weapon pressure")
        if now > self.deadline and self.phase not in ("hold", "exit"):
            self.begin_exit(obs, circle, "flight phase timed out")
        if self.phase == "ascend":
            if p[2] >= entry[2]+1.2:
                self.phase, self.deadline, self.cross_started = "cross", now+4, now
            else:
                return {"move": self._move_to(me, launch, .25), "boost": True, "jump": False}
        if self.phase == "cross":
            if (distance(p, entry) < 3 and site["prism"].contains(*p[:2])) or (
                    me["grounded"] and p[2] >= entry[2]-.5 and site["prism"].contains(*p[:2])):
                self.phase, self.deadline = "land", now+5
            else:
                predicted = p[2]+me["vel"][2]*.3-stats["gravity"]*.3*.3/2
                jet = now-self.cross_started < .45 or (
                    not site["prism"].contains(*p[:2]) and predicted < entry[2]+.5)
                return {"move": list(unit(entry[0]-p[0], entry[1]-p[1])),
                        "boost": bool(jet), "jump": False}
        if self.phase == "land":
            if me["grounded"] and abs(p[2]-entry[2]) < 1.5:
                self.phase = "settle"
                self.deadline = now+max(10, distance(p, hold)/max(1, stats["walk_speed"])*1.6+4)
            elif me["grounded"] and p[2] < entry[2]-3:
                self.cancel(now, True, "missed the roof and returned to ground")
                return None
            else:
                return {"move": self._move_to(me, entry), "boost": False, "jump": False}
        if self.phase == "settle":
            if p[2] < entry[2]-3:
                self.begin_exit(obs, circle, "fell below intended roof")
            elif distance(p, hold) < 1.5:
                if math.hypot(*me["vel"][:2]) < 1.5:
                    self.phase, self.deadline = "hold", math.inf
                else:
                    return {"move": [0, 0], "boost": False, "jump": False}
            else:
                return {"move": self._move_to(me, hold), "boost": False, "jump": False}
        if self.phase == "hold":
            if not self.valid_site(site, me) or p[2] < entry[2]-3 or not me["grounded"]:
                self.begin_exit(obs, circle, "live body or support invalidated refuge")
            else:
                move = [0, 0] if distance(p, hold) < 1.5 else self._move_to(me, hold)
                return {"move": move, "boost": False, "jump": False}
        if self.phase == "exit":
            ground = self.world.ground(*p[:2])
            if me["grounded"] and p[2] <= ground+stats["step_up"]+.5:
                self.cancel(now, False, "grounded after roof exit")
                return None
            if self.exit_progress_position is None or math.dist(p, self.exit_progress_position) >= 1.5:
                self.exit_progress_position = tuple(p)
                self.exit_progress_at = now
                # A wide roof may require more than twelve seconds of genuine
                # progress. Extend the watchdog rather than abandon its surface.
                remaining = distance(p, self.exit_entry or self.exit_goal or launch)
                self.deadline = now+max(6, remaining/max(1, stats["walk_speed"])*1.6+4)
            if me["grounded"] and (now > self.deadline or now-self.exit_progress_at > 2.5):
                self.failed_exits[id(self.exit_site or site)] = now+15
                self.begin_exit(obs, circle, "exit stalled; retry another physical roof edge")
            if self.exit_entry is not None:
                if distance(p, self.exit_entry) > 2 and p[2] >= entry[2]-1.5:
                    return {"move": self._move_to(me, self.exit_entry, .3),
                            "boost": False, "jump": False}
                self.exit_entry = None
            goal = self.exit_goal or launch
            return {"move": self._move_to(me, goal, .35), "boost": False, "jump": False}
        return None
