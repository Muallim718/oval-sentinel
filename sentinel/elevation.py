"""A bounded roof-escape controller: approach, climb, cross, land, recover.

This deliberately handles nearby single-roof escapes, not arbitrary aerial paths.
All sites derive from public map solids. Energy and body clearance are rechecked
using current upgraded stats before starting a flight.
"""
import math
from .geometry import distance, unit


class RoofEscape:
    def __init__(self, world, mech):
        self.world = world
        self.sites = self.find_sites(mech)
        self.site = None
        self.phase = None
        self.deadline = -1
        self.next_search = -1
        self.failed = {}
        self.best_height = -math.inf
        self.last_rise = 0

    def find_sites(self, stats):
        sites = []
        radius, height = stats["radius"]+0.8, stats["height"]
        for prism in self.world.prisms:
            if prism.kind == "bridge":
                continue
            # Long outer edges provide usable launch columns and landing room.
            long_edges = sorted(prism.outer,key=lambda edge:distance(*edge),reverse=True)[:3]
            for a,b in long_edges:
                length = distance(a,b)
                if length < 14:
                    continue
                nx,ny = -(b[1]-a[1])/length, (b[0]-a[0])/length
                mx,my = (a[0]+b[0])/2,(a[1]+b[1])/2
                if not prism.contains(mx+nx,my+ny):
                    nx,ny = -nx,-ny
                launch = (mx-nx*(radius+2),my-ny*(radius+2))
                low = self.world.ground(*launch)
                rise = prism.top-low
                if not 7 < rise < 43:
                    continue
                landing = (mx+nx*(radius+7),my+ny*(radius+7),prism.top)
                if not prism.contains(*landing[:2]):
                    continue
                if not self.world.body_clear(*landing,radius,height,0):
                    continue
                if not self.world.vertical_clear(*launch,low,prism.top+1,radius,height):
                    continue
                # No taller obstruction may interrupt the lateral crossing.
                start = (*launch,prism.top+1)
                if not self.world.walk_clear(start,(*landing[:2],prism.top+1),radius,height,0):
                    continue
                sites.append({"launch":(*launch,low),"landing":landing,"prism":prism})
        return sites

    def cancel(self, now, failed=False):
        if failed and self.site:
            self.failed[id(self.site)] = now+30
        self.site, self.phase = None, None
        self.next_search = now+3

    @staticmethod
    def energy_needed(site, me):
        s = me["stats"]
        rise = max(0,site["landing"][2]-me["pos"][2])
        # Include horizontal crossing and a reserve; do not spend the last joule
        # reaching an edge with no way to get safely inside it.
        flight = rise/max(1,s["max_rise_speed"])+1.7
        return flight*s["jet_drain"]+14

    def safe_in_zone(self, site, circle):
        return all(distance(site[key],circle[0]) < circle[1]-10 for key in ("launch","landing"))

    def choose(self, obs, threats, circle):
        me,now = obs["self"],obs["t"]
        s,p = me["stats"],me["pos"]
        options = []
        for site in self.sites:
            if self.failed.get(id(site),-1) > now:
                continue
            travel = distance(p,site["launch"])
            if travel > 60 or not self.safe_in_zone(site,circle):
                continue
            if site["landing"][2] < p[2]+5:
                continue
            if self.energy_needed(site,me) > me["energy"]:
                continue
            launch,land = site["launch"],site["landing"]
            r,h = s["radius"]+0.6,s["height"]
            if not self.world.body_clear(*land,r,h,0):
                continue
            if not self.world.vertical_clear(*launch[:2],launch[2],land[2]+1,r,h):
                continue
            score = travel*0.6 + (land[2]-launch[2])*0.15
            occupied = False
            for enemy,confidence in threats[:5]:
                ep = enemy["pos"]
                d = distance(launch,ep)
                score += max(0,45-d)*confidence
                if self.world.line_clear([land[0],land[1],land[2]+h/2],
                                         [ep[0],ep[1],ep[2]+7]):
                    score += max(0,155-distance(land,ep))*0.4*confidence
                if ep[2] > land[2]-5 and distance(land,ep) < 35:
                    occupied = True
            if not occupied:
                options.append((score,site))
        if options:
            return min(options,key=lambda pair:pair[0])[1]
        return None

    def update(self, obs, threats, circle, need_escape):
        """Return an approach waypoint or flight controls, or None for ground AI."""
        me,now = obs["self"],obs["t"]
        p,s = me["pos"],me["stats"]
        if self.site is None:
            if not need_escape or not me["grounded"] or now < self.next_search or me["energy"] < 58:
                return None
            self.next_search = now+2
            self.site = self.choose(obs,threats,circle)
            if self.site is None:
                return None
            self.phase,self.deadline = "approach",now+12
        site = self.site
        if not self.safe_in_zone(site,circle) or now > self.deadline:
            self.cancel(now,True)
            return None
        launch,land = site["launch"],site["landing"]
        if self.phase == "approach":
            if distance(p,launch) > 2.3:
                return {"approach":launch}
            if not me["grounded"]:
                return {"approach":launch}
            if self.energy_needed(site,me) > me["energy"]:
                self.cancel(now,True)
                return None
            self.phase,self.deadline = "climb",now+8
            self.best_height,self.last_rise = p[2],now
            return {"move":[0,0],"jump":True,"boost":True}
        if self.phase in ("climb","cross"):
            if p[2] > self.best_height+0.4:
                self.best_height,self.last_rise = p[2],now
            if me["energy"] < 9 or (self.phase == "climb" and now-self.last_rise > 1.4):
                self.cancel(now,True)
                return None
        if self.phase == "climb":
            if p[2] >= land[2]+1:
                self.phase,self.deadline = "cross",now+3
            else:
                # Stabilize outside the wall instead of jetting under its eave.
                dx,dy = launch[0]-p[0],launch[1]-p[1]
                move = [max(-.5,min(.5,dx*.3-me["vel"][0]*.08)),
                        max(-.5,min(.5,dy*.3-me["vel"][1]*.08))]
                return {"move":move,"boost":True,"jump":False}
        if self.phase == "cross":
            if distance(p,land) < 2.8 and site["prism"].contains(*p[:2]):
                self.phase,self.deadline = "land",now+5
            else:
                return {"move":list(unit(land[0]-p[0],land[1]-p[1])),"boost":True,"jump":False}
        if self.phase == "land":
            if me["grounded"] and abs(p[2]-land[2]) < 2:
                self.phase,self.deadline = "rest",now+25
            elif me["grounded"] and p[2] < land[2]-3:
                self.cancel(now,True)
                return None
            else:
                move = [max(-1,min(1,(land[0]-p[0])*.2-me["vel"][0]*.12)),
                        max(-1,min(1,(land[1]-p[1])*.2-me["vel"][1]*.12))]
                return {"move":move,"boost":False,"jump":False}
        if self.phase == "rest":
            if me["hp"] >= me["max_hp"]*.96 and me["energy"] >= me["max_energy"]*.75:
                self.cancel(now)
                return None
            if not me["grounded"] or p[2] < land[2]-3:
                self.cancel(now,True)
                return None
            return {"move":[0,0],"boost":False,"jump":False}
        return None
