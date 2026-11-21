"""Static map geometry: terrain, solid prisms, and a spatial index.

Trees are deliberately excluded: they block vision, but never movement or shots.
Ground navigation is conservative. Exact local checks also handle rooftops and
bridges, and scale the mech's body from its live stats.
"""
from array import array
import json
import math
from pathlib import Path
import sys


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-8 else (0.0, 0.0)


def angle_error(a, b):
    return (a - b + math.pi) % math.tau - math.pi


def edges(ring):
    points = list(zip(ring[::2], ring[1::2]))
    return list(zip(points, points[1:] + points[:1]))


def inside(x, y, segments):
    result = False
    for (ax, ay), (bx, by) in segments:
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            result = not result
    return result


def segment_distance_sq(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx*dx + dy*dy or 1)))
    return (x - a[0] - t*dx)**2 + (y - a[1] - t*dy)**2


class Prism:
    def __init__(self, data):
        self.base, self.top = data["base"], data["top"]
        self.outer = edges(data["ring"])
        self.holes = [edges(h) for h in data.get("holes", [])]
        self.all_edges = self.outer + [edge for hole in self.holes for edge in hole]
        xs, ys = data["ring"][::2], data["ring"][1::2]
        self.bounds = min(xs), min(ys), max(xs), max(ys)

    def contains(self, x, y):
        a, b, c, d = self.bounds
        return (a <= x <= c and b <= y <= d and inside(x, y, self.outer)
                and not any(inside(x, y, h) for h in self.holes))

    def overlaps(self, x, y, radius):
        a, b, c, d = self.bounds
        if x < a-radius or x > c+radius or y < b-radius or y > d+radius:
            return False
        return self.contains(x, y) or any(
            segment_distance_sq(x, y, p, q) < radius*radius for p, q in self.all_edges)

    def blocks_segment(self, a, b):
        # Clip to this prism's vertical extent, then intersect the polygon in XY.
        dz = b[2] - a[2]
        lo, hi = 0.0, 1.0
        if abs(dz) < 1e-10:
            if not self.base < a[2] < self.top:
                return False
        else:
            t1, t2 = (self.base-a[2])/dz, (self.top-a[2])/dz
            lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
            if lo > hi:
                return False
        dx, dy = b[0]-a[0], b[1]-a[1]
        for t in (lo, hi, (lo+hi)/2):
            if self.contains(a[0]+dx*t, a[1]+dy*t):
                return True
        for (px, py), (qx, qy) in self.all_edges:
            ex, ey = qx-px, qy-py
            det = dx*ey-dy*ex
            if abs(det) < 1e-10:
                continue
            rx, ry = px-a[0], py-a[1]
            t, u = (rx*ey-ry*ex)/det, (rx*dy-ry*dx)/det
            if lo <= t <= hi and 0 <= u <= 1:
                return True
        return False


class World:
    CELL = 24

    def __init__(self, directory):
        root = Path(directory) / "v2"
        data = json.loads((root / "world.json").read_text(encoding="utf-8"))
        self.bounds = data["bounds"]
        self.terrain = data["terrain"]
        self.heights = array("h")
        self.heights.frombytes((root / "terrain.i16").read_bytes())
        if sys.byteorder != "little":
            self.heights.byteswap()
        if len(self.heights) != self.terrain["nx"] * self.terrain["ny"]:
            raise ValueError("terrain dimensions do not match terrain.i16")
        self.prisms = [Prism(p) for p in data["prisms"]]
        self.buckets = {}
        for index, p in enumerate(self.prisms):
            x1, y1, x2, y2 = p.bounds
            for j in range(math.floor(y1/self.CELL), math.floor(y2/self.CELL)+1):
                for i in range(math.floor(x1/self.CELL), math.floor(x2/self.CELL)+1):
                    self.buckets.setdefault((i, j), []).append(index)

    def nearby(self, x, y, radius=0):
        ids = set()
        for j in range(math.floor((y-radius)/self.CELL), math.floor((y+radius)/self.CELL)+1):
            for i in range(math.floor((x-radius)/self.CELL), math.floor((x+radius)/self.CELL)+1):
                ids.update(self.buckets.get((i, j), ()))
        return (self.prisms[i] for i in ids)

    def ground(self, x, y):
        t = self.terrain
        gx = max(0, min(t["nx"]-1.000001, (x-t["minX"])/t["step"]))
        gy = max(0, min(t["ny"]-1.000001, (y-t["minY"])/t["step"]))
        i, j = int(gx), int(gy)
        fx, fy = gx-i, gy-j
        k, nx = j*t["nx"]+i, t["nx"]
        h = self.heights
        return ((h[k]*(1-fx)+h[k+1]*fx)*(1-fy) +
                (h[k+nx]*(1-fx)+h[k+nx+1]*fx)*fy) * t.get("scale", 0.01)

    def body_clear(self, x, y, z, radius=2.8, height=9, step=1.2):
        b = self.bounds
        if not (b["minX"]+radius < x < b["maxX"]-radius and
                b["minY"]+radius < y < b["maxY"]-radius):
            return False
        return not any(p.top > z+step and p.base < z+height-0.05 and p.overlaps(x, y, radius)
                       for p in self.nearby(x, y, radius))

    def walk_clear(self, a, b, radius=2.8, height=9, step=1.2, slope=50):
        length = distance(a, b)
        n = max(1, math.ceil(length/1.5))
        previous_z = a[2]
        for i in range(1, n+1):
            t = i/n
            x, y = a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t
            # Elevated mechs may walk off a roof; ground paths follow terrain.
            ground = self.ground(x, y)
            z = max(ground, a[2]) if a[2] > self.ground(*a[:2])+step else ground
            if (z-previous_z > max(step, math.tan(math.radians(slope))*length/n) or
                    not self.body_clear(x, y, z, radius, height, step)):
                return False
            previous_z = z
        return True

    def line_clear(self, a, b):
        # Spatially gather prisms along the ray; then test exact polygon crossings.
        count = max(1, math.ceil(distance(a, b)/(self.CELL/2)))
        ids = set()
        for i in range(count+1):
            t = i/count
            x, y = a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t
            ids.update(self.buckets.get((math.floor(x/self.CELL), math.floor(y/self.CELL)), ()))
        if any(self.prisms[i].blocks_segment(a, b) for i in ids):
            return False
        # Terrain sampling is approximate; use 2 m spacing to catch hills.
        count = max(1, math.ceil(distance(a, b)/2))
        for i in range(1, count):
            t = i/count
            if a[2]+(b[2]-a[2])*t < self.ground(a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t):
                return False
        return True
