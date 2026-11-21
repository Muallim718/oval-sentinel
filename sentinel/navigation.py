"""Bounded A* on a cached ground grid, followed by body-aware local steering."""
import heapq
import math
import time
from .geometry import distance
from . import tuning


class Navigator:
    def __init__(self, world, mech):
        self.world = world
        self.step = tuning.GRID_STEP
        b = world.bounds
        self.x0, self.y0 = b["minX"]+4, b["minY"]+4
        self.nx = int((b["maxX"]-self.x0-4)/self.step)+1
        self.ny = int((b["maxY"]-self.y0-4)/self.step)+1
        self.points, self.valid = [], bytearray(self.nx*self.ny)
        self.radius = mech["radius"] + 0.4
        self.height = mech["height"]
        self.step_up = mech["step_up"]
        for j in range(self.ny):
            for i in range(self.nx):
                x, y = self.x0+i*self.step, self.y0+j*self.step
                z = world.ground(x, y)
                self.points.append((x, y, z))
                self.valid[j*self.nx+i] = world.body_clear(x, y, z, self.radius, self.height, self.step_up)
        # Connections are checked lazily, then cached for the rest of the match.
        self.links = {}
        self.path = []
        self.goal = None
        self.next_plan = -1
        self.search = None
        self.search_done = True

    def nearest(self, pos):
        i = max(0, min(self.nx-1, round((pos[0]-self.x0)/self.step)))
        j = max(0, min(self.ny-1, round((pos[1]-self.y0)/self.step)))
        best, best_d = None, math.inf
        for r in range(9):
            for y in range(max(0, j-r), min(self.ny, j+r+1)):
                for x in range(max(0, i-r), min(self.nx, i+r+1)):
                    if r and abs(x-i) != r and abs(y-j) != r:
                        continue
                    k = y*self.nx+x
                    if self.valid[k]:
                        d = distance(pos, self.points[k])
                        if d < best_d:
                            best, best_d = k, d
            if best is not None:
                return best
        return None

    def neighbors(self, k):
        if k not in self.links:
            i, j = k % self.nx, k // self.nx
            out = []
            for dx, dy in ((1,0), (-1,0), (0,1), (0,-1), (1,1), (1,-1), (-1,1), (-1,-1)):
                x, y = i+dx, j+dy
                if not (0 <= x < self.nx and 0 <= y < self.ny):
                    continue
                other = y*self.nx+x
                if not self.valid[other]:
                    continue
                if dx and dy and not (self.valid[j*self.nx+x] and self.valid[y*self.nx+i]):
                    continue
                if self.world.walk_clear(self.points[k], self.points[other], self.radius, self.height, self.step_up):
                    out.append((other, self.step * (math.sqrt(2) if dx and dy else 1)))
            self.links[k] = out
        return self.links[k]

    def plan(self, pos, goal, circle, threats=()):
        start, end = self.nearest(pos), self.nearest(goal)
        if start is None or end is None:
            return []
        target = self.points[end]
        if self.search is None or self.search[0] != end:
            self.search = (end, [(distance(self.points[start], target), start)],
                           {start: 0.0}, {}, set(), [start, distance(self.points[start], target)])
        _, frontier, costs, parents, visited, progress = self.search
        best, best_h = progress
        self.search_done = False
        deadline = time.perf_counter() + tuning.PLAN_SECONDS
        for _ in range(tuning.PLAN_EXPANSIONS):
            if not frontier or time.perf_counter() >= deadline:
                break
            _, current = heapq.heappop(frontier)
            if current in visited:
                continue
            visited.add(current)
            h = distance(self.points[current], target)
            if h < best_h:
                best, best_h = current, h
            if current == end:
                best = end
                self.search_done = True
                break
            for other, length in self.neighbors(current):
                p = self.points[other]
                outside = max(0.0, distance(p, circle[0])-circle[1])
                danger = sum(max(0, 65-distance(p, e))/65 for e in threats)
                cost = costs[current] + length*(1+min(12, outside/8)+danger*2)
                if cost < costs.get(other, math.inf):
                    costs[other], parents[other] = cost, current
                    heapq.heappush(frontier, (cost+1.12*distance(p, target), other))
        if not frontier:
            self.search_done = True
        progress[:] = best, best_h
        route = [best]
        while route[-1] in parents:
            route.append(parents[route[-1]])
        points = [self.points[k] for k in reversed(route)]
        # A search may span several decisions while the mech is already moving.
        # Discard the part of the old route now behind it.
        closest = min(range(len(points)), key=lambda i: distance(pos, points[i]))
        return points[closest:][1:] if distance(pos, points[closest]) < 5 else points[closest:]

    def waypoint(self, pos, goal, now, circle, threats):
        direct = (goal[0], goal[1], self.world.ground(*goal[:2]))
        if distance(pos, goal) < 85 and self.world.walk_clear(pos, direct, self.radius, self.height, self.step_up):
            return direct
        moved = self.goal is None or distance(goal, self.goal) > 15
        if moved or (self.search_done and (now >= self.next_plan or not self.path)):
            self.search = None
        if moved or now >= self.next_plan or not self.path or not self.search_done:
            self.path = self.plan(pos, goal, circle, threats)
            self.goal, self.next_plan = goal, now+1.0
        while self.path and distance(pos, self.path[0]) < 5:
            self.path.pop(0)
        # Aim for a reachable later waypoint to avoid grid-shaped walking.
        for p in reversed(self.path[:5]):
            if self.world.walk_clear(pos, p, self.radius, self.height, self.step_up):
                return p
        return self.path[0] if self.path else goal
