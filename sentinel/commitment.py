"""Short lethal commitments backed by observed trades and current ready weapons.

This is a bounded opportunity detector, not a full enemy build/TTK simulator.
The caller supplies real shot feasibility and keeps movement/escape authority.
"""
from collections import deque
import math

from .geometry import angle_error, distance


class State:
    WINDOW = 3.0
    MAX_HORIZON = 2.0
    MAX_COMMITMENT = 2.5
    MIN_TRADE_RATIO = 1.25
    WEAPONS = {"gun", "laser", "mortar", "lightning"}

    def __init__(self, config):
        self.config = config
        self.hits = deque(maxlen=96)
        self.taken = deque(maxlen=96)
        self.gun_shots = deque(maxlen=64)
        self.pending = deque(maxlen=32)
        self.laser_fired = {}
        self.previous_ammo = None
        self.previous_tick = None
        self.dead = set()
        self.blocked_until = {}
        self.target_id = None
        self.weapon_kind = None
        self.deadline = -1
        self.horizon = None
        self.incoming_budget = 0
        self.accuracy = .65
        self.started_at = -1
        self.proof_dealt = self.proof_taken = 0
        self.reason = "no observed lethal opportunity"

    def _prune(self, now):
        for queue in (self.hits, self.taken, self.gun_shots):
            while queue and now-queue[0][0] > self.WINDOW:
                queue.popleft()
        self.blocked_until = {key: until for key, until in self.blocked_until.items() if until > now}
        self.pending = deque((shot for shot in self.pending if now <= shot[4]), maxlen=32)

    def update(self, obs):
        """Consume each observation once; only our hit events prove our trade."""
        marker = (obs["tick"], obs["t"])
        if marker == self.previous_tick:
            return
        self.previous_tick = marker
        now, me = obs["t"], obs["self"]
        unmatched_gun_hits = {}
        for event in obs["events"]:
            kind, weapon = event["type"], event.get("weapon")
            if kind == "hit" and weapon in self.WEAPONS and event.get("amount", 0) > 0:
                target = event["target"]
                if isinstance(target, int) and 0 <= target < 16 and target != me["id"]:
                    self.hits.append((now, target, event["amount"], weapon))
                    if weapon == "gun":
                        removed = False
                        remaining = []
                        for shot in self.pending:
                            if not removed and shot[1] == target:
                                removed = True
                            else:
                                remaining.append(shot)
                        self.pending = deque(remaining, maxlen=32)
                        if not removed:
                            unmatched_gun_hits[target] = unmatched_gun_hits.get(target, 0)+1
            elif kind == "damaged" and weapon in self.WEAPONS | {"npc"} and event.get("amount", 0) > 0:
                attacker = event.get("by")
                self.taken.append((now, attacker, event["amount"], weapon))
                if weapon == "laser" and attacker is not None:
                    self.laser_fired[attacker] = now
            elif kind == "kill":
                self.dead.add(event["target"])
                if event["target"] == self.target_id:
                    self._clear("confirmed kill; release focus")
        for beam in obs.get("beams", []):
            if beam["kind"] == "laser" and beam["by"] != me["id"]:
                fired = now-max(0, beam.get("age", 0))
                self.laser_fired[beam["by"]] = max(fired, self.laser_fired.get(beam["by"], -100))
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if gun:
            ammo = gun.get("ammo", 0)
            if self.previous_ammo is not None and ammo < self.previous_ammo:
                count = self.previous_ammo-ammo
                self.gun_shots.append((now, count))
                focus = next((enemy for enemy in obs["mechs"] if enemy["id"] == self.target_id), None)
                if self.weapon_kind == "gun" and focus is not None:
                    flight = distance(me["pos"], focus["pos"])/gun["stats"]["speed"]
                    multiplier = 1+self.config["cubes"]["damage_per_cube"]*min(
                        me["cubes"], self.config["cubes"]["stat_cap"])
                    # A nearby projectile can be fired and hit in the same
                    # observation window. Do not credit that confirmed hit twice.
                    unconfirmed = max(0, count-unmatched_gun_hits.get(self.target_id, 0))
                    for _ in range(min(12, unconfirmed)):
                        self.pending.append((now, self.target_id,
                            gun["stats"]["damage"]*multiplier*self.accuracy,
                            now+flight, now+flight+.2))
            self.previous_ammo = ammo
        else:
            self.previous_ammo = None
        self._prune(now)

    def _clear(self, reason):
        self.target_id = self.weapon_kind = None
        self.deadline = -1
        self.horizon = None
        self.incoming_budget = 0
        self.proof_dealt = self.proof_taken = 0
        self.reason = reason

    def _abort(self, now, reason):
        if self.target_id is not None:
            self.blocked_until[self.target_id] = now+.6
        self._clear(reason)

    def cancel(self, reason="ordinary policy regained control"):
        """End the forced target/weapon window and all unconfirmed shot credit."""
        self.pending.clear()
        self._clear(reason)

    def _acquire(self, me, target, solution):
        if isinstance(solution, (tuple, list)) and len(solution) == 4:
            aim = solution[0]
        else:
            p, q = me["pos"], target["pos"]
            scale = 1+self.config["cubes"]["size_per_cube"]*target.get("cubes", 0)
            dz = q[2]+self.config["mech"]["height"]*scale*.5-p[2]-me["stats"]["muzzle_height"]
            aim = (math.atan2(q[1]-p[1], q[0]-p[0]), math.atan2(dz, distance(p, q)))
        stats = me["stats"]
        if not stats["min_pitch"] <= aim[1] <= stats["max_pitch"]:
            return math.inf
        return max(abs(angle_error(aim[0], me["aim"][0]))/stats["turn_rate"],
                   abs(aim[1]-me["aim"][1])/stats["pitch_rate"])

    def _plans(self, obs, target, can_hit):
        me = obs["self"]
        dealt = [hit for hit in self.hits if hit[1] == target["id"]]
        spent = sum(count for _, count in self.gun_shots)
        gun_hits = sum(hit[3] == "gun" for hit in dealt)
        accuracy = (self.accuracy if self.target_id == target["id"] else
                    min(.95, max(.35, gun_hits/spent)) if spent else .65)
        cube_mult = 1+self.config["cubes"]["damage_per_cube"]*min(
            me["cubes"], self.config["cubes"]["stat_cap"])
        plans = []
        for weapon in me["weapons"]:
            if not weapon or weapon["kind"] not in ("gun", "laser"):
                continue
            solution = can_hit(target, weapon)
            if not solution:
                continue
            acquire = self._acquire(me, target, solution)
            stats = weapon["stats"]
            if weapon["kind"] == "gun" and len(dealt) >= 2:
                pending = [shot for shot in self.pending if shot[1] == target["id"]]
                remaining_hp = max(0, target["hp"]-sum(shot[2] for shot in pending))
                needed = math.ceil(remaining_hp/(stats["damage"]*cube_mult*accuracy))
                if needed == 0 and pending:
                    horizon = max(.05, max(shot[3] for shot in pending)-obs["t"]+.1)
                    plans.append((horizon, "gun", accuracy))
                elif needed <= weapon.get("ammo", 0) and weapon.get("reload", 0) <= 0:
                    first = max(.05, math.ceil(weapon.get("cooldown", 0)/.05)*.05, acquire+.05)
                    horizon = first+(needed-1)*stats["cooldown"]+distance(me["pos"], target["pos"])/stats["speed"]+.05
                    if horizon <= self.MAX_HORIZON:
                        plans.append((horizon, "gun", accuracy))
            elif weapon["kind"] == "laser" and weapon.get("cooldown", 0) <= 0:
                charge = weapon.get("charge", 0)
                fraction = stats["min_frac"]+(1-stats["min_frac"])*min(1, charge/stats["charge"])
                # Use charge already present; never assume a new charge can be
                # started safely, or halve escape speed to manufacture a finish.
                if (charge >= stats["min_charge"] and acquire <= .15 and
                        target["hp"] <= stats["damage"]*cube_mult*fraction*.9):
                    plans.append((acquire+.10, "laser", 1.0))
        return sorted(plans)

    def _pressure(self, obs, target, horizon, projectile_damage):
        """A short counter-burst budget, with observed laser cooldown evidence."""
        me, now = obs["self"], obs["t"]
        window = horizon+.15
        scale = 1+self.config["cubes"]["damage_per_cube"]*min(
            target.get("cubes", 0), self.config["cubes"]["stat_cap"])
        armor = max(.25, 1-me["stats"].get("armor", 0))
        kinds = target.get("weapons", ["gun"])
        budget = max(0, projectile_damage)
        for kind in kinds:
            if kind not in self.WEAPONS:
                continue
            stats = self.config["weapons"][kind]
            observed = max((hit[2] for hit in self.taken if hit[1] == target["id"] and hit[3] == kind), default=0)
            damage = max(stats["damage"]*scale*armor, observed)
            if kind == "gun":
                budget += damage*(math.ceil(window/stats["cooldown"])+1)
            elif kind == "laser":
                next_ready = self.laser_fired.get(target["id"], -100)+stats["cooldown"]
                if target.get("charging") or next_ready <= now+window:
                    budget += damage
            elif kind == "mortar":
                budget += damage+stats["splash"]*scale*armor
            elif distance(me["pos"], target["pos"]) <= stats["range"]+20*window:
                budget += damage*(math.ceil(window/stats["cooldown"])+1)
        recent = sum(hit[2] for hit in self.taken if hit[1] == target["id"])
        return max(budget, recent/self.WINDOW*window+max(0, projectile_damage))

    def choose(self, obs, threats=(), *, can_hit=None, exposed=None,
               zone_safe=True, projectile_damage=0):
        """Return a short lethal focus, or None; do not choose movement or fire.

        can_hit(target, weapon) must report real shot feasibility; it may return
        a Combat.solve tuple, allowing exact acquisition time. exposed(enemy)
        may supply incoming line-of-fire knowledge. Without it, known nearby
        other mechs conservatively veto commitment. No callback means no plan.
        """
        me, now = obs["self"], obs["t"]
        self._prune(now)
        if can_hit is None or not zone_safe or not me["in_zone"]:
            self._abort(now, "shot or zone feasibility unavailable")
            return None
        if self.target_id is not None and now > self.deadline:
            self._abort(now, "lethal commitment deadline expired")
            return None
        targets = [e for e in obs["mechs"] if e.get("kind") == "mech" and
                   e["id"] not in self.dead and e.get("hp", 0) > 0]
        targets.sort(key=lambda e: (e["id"] != self.target_id, e["hp"], distance(me["pos"], e["pos"])))
        known = {e["id"]: e for e, confidence in threats if e.get("kind") == "mech" and confidence >= .35}
        known.update({e["id"]: e for e in targets})
        for target in targets[:4]:
            target_id = target["id"]
            if self.target_id is not None and target_id != self.target_id:
                continue
            if self.blocked_until.get(target_id, -1) > now:
                continue
            if any(now-hit[0] < 1 and hit[1] != target_id for hit in self.taken):
                continue
            if any(e["id"] != target_id and distance(me["pos"], e["pos"]) < 230 and
                   (distance(me["pos"], e["pos"]) < 35 or exposed is None or exposed(e))
                   for e in known.values()):
                continue
            dealt = [hit for hit in self.hits if hit[1] == target_id]
            taken = sum(hit[2] for hit in self.taken if hit[1] == target_id)
            amount = sum(hit[2] for hit in dealt)
            if self.target_id == target_id:
                effective_dealt = self.proof_dealt+sum(hit[2] for hit in dealt if hit[0] > self.started_at)
                effective_taken = self.proof_taken+sum(hit[2] for hit in self.taken
                    if hit[1] == target_id and hit[0] > self.started_at)
                favorable = effective_dealt >= self.MIN_TRADE_RATIO*effective_taken
            else:
                favorable = (len(dealt) >= 2 and dealt[-1][0]-dealt[0][0] >= .35 and
                              now-dealt[-1][0] <= .8 and amount >= self.MIN_TRADE_RATIO*taken)
            for horizon, kind, accuracy in self._plans(obs, target, can_hit):
                if kind == "gun" and not favorable:
                    continue
                budget = self._pressure(obs, target, horizon, projectile_damage)
                if me["hp"]-budget <= max(200, me["max_hp"]*.20):
                    continue
                if self.target_id is None:
                    self.deadline = now+min(self.MAX_COMMITMENT, horizon+.4)
                    self.started_at = now
                    self.proof_dealt, self.proof_taken = amount, taken
                    self.accuracy = accuracy
                self.target_id, self.weapon_kind = target_id, kind
                self.horizon, self.incoming_budget = horizon, budget
                self.reason = ("observed favorable trade and ready lethal gun" if kind == "gun"
                               else "already charged lethal laser with pressure reserve")
                return target
        self._abort(now, "trade, ready burst, or incoming pressure no longer supports a finish")
        return None
