"""Conservative early engagement evidence, separate from full threat safety.

A far mech is discounted only after continuous observations show it looking and
moving elsewhere. This never labels house roles or removes enemies from escape
planning. The caller supplies its current geometrically exposed enemy list.
"""
import math

from .geometry import angle_error, distance


class EarlyPressure:
    EARLY_SECONDS = 75.0
    MIN_ALIVE = 12
    PASSER_SECONDS = .6
    MAX_GAP = .25
    FAR_METERS = 90.0
    AWAY_ANGLE = math.pi/3
    MAX_CLOSING = 1.0
    MAX_TURN_RATE = .18
    ATTACK_MEMORY = 5.0

    def __init__(self, config):
        self.config = config
        self.history = {}
        self.attacked_at = {}
        self.eligible = False
        self.ignored = set()
        self.reason = "all geometric threats retained"
        self.last_observation = None

    def _conditions(self, enemy, me):
        if (enemy.get("kind") != "mech" or enemy.get("charging")
                or "aim" not in enemy or "vel" not in enemy):
            return False
        dx, dy = me["pos"][0]-enemy["pos"][0], me["pos"][1]-enemy["pos"][1]
        d = math.hypot(dx, dy)
        if d < self.FAR_METERS:
            return False
        error = abs(angle_error(math.atan2(dy, dx), enemy["aim"][0]))
        if error <= self.AWAY_ANGLE:
            return False
        # This measures the other mech's approach intent. Our own movement
        # must not make a stationary passer flicker into a new pursuer. Actual
        # separation is independently guarded by the 90-meter distance veto.
        closing = (enemy["vel"][0]*dx+enemy["vel"][1]*dy)/max(1, d)
        return closing <= self.MAX_CLOSING

    def _incoming(self, obs):
        """Visible trajectories are physical evidence, without invented owners."""
        me = obs["self"]
        result = []
        projectiles = sorted(obs.get("projectiles", ()),
                             key=lambda p: distance(me["pos"], p["pos"]))[:64]
        for p in projectiles:
            if p.get("kind") not in ("gun", "mortar"):
                continue
            vx, vy = p["vel"][:2]
            rx, ry = p["pos"][0]-me["pos"][0], p["pos"][1]-me["pos"][1]
            rvx, rvy = vx-me.get("vel", [0, 0])[0], vy-me.get("vel", [0, 0])[1]
            dot = rx*rvx+ry*rvy
            if dot >= 0:
                continue
            t = min(1.5, -dot/max(1, rvx*rvx+rvy*rvy))
            radius = me["stats"]["radius"]+(9 if p["kind"] == "mortar" else 4)
            if math.hypot(rx+rvx*t, ry+rvy*t) <= radius:
                result.append(p)
        return result

    def _near_firing_lane(self, enemy, projectiles):
        # A new bullet leaving near this mech on a line toward us is a reason
        # to retain the lane. It is not asserted to belong to that mech; an
        # ambiguous collinear shot conservatively keeps both possible threats.
        for p in projectiles:
            rx, ry = p["pos"][0]-enemy["pos"][0], p["pos"][1]-enemy["pos"][1]
            if math.hypot(rx, ry) > 32:
                continue
            vx, vy = p["vel"][:2]
            along = rx*vx+ry*vy
            if along < 0:
                continue
            back = along/max(1, vx*vx+vy*vy)
            if math.hypot(rx-vx*back, ry-vy*back) < 7:
                return True
        return False

    def update(self, obs):
        now, me = obs["t"], obs["self"]
        key = (obs.get("tick"), now)
        if key == self.last_observation:
            return
        self.last_observation = key
        self.ignored = set()
        self.eligible = (0 <= now <= self.EARLY_SECONDS and
                         obs.get("alive", 0) >= self.MIN_ALIVE)
        for event in obs.get("events", ()):
            if event.get("type") in ("damaged", "effect") and event.get("by") is not None:
                self.attacked_at[event["by"]] = now
        for beam in obs.get("beams", ()):
            if beam.get("by") is not None:
                self.attacked_at[beam["by"]] = max(
                    self.attacked_at.get(beam["by"], -100), now-beam.get("age", 0))
        self.attacked_at = {i: t for i, t in self.attacked_at.items()
                            if now-t <= self.ATTACK_MEMORY}
        if not self.eligible:
            self.history.clear()
            self.reason = "outside conservative early phase"
            return
        projectiles = self._incoming(obs)
        current = {}
        for enemy in obs.get("mechs", ()):
            if enemy.get("kind") != "mech":
                continue
            ident = enemy["id"]
            previous = self.history.get(ident)
            continuous = previous is not None and 0 < now-previous["at"] <= self.MAX_GAP
            if self._near_firing_lane(enemy, projectiles):
                self.attacked_at[ident] = now
            quiet = now-self.attacked_at.get(ident, -100) > self.ATTACK_MEMORY
            qualifies = quiet and self._conditions(enemy, me)
            if qualifies and continuous:
                turn = abs(angle_error(enemy["aim"][0], previous["yaw"]))/max(.001, now-previous["at"])
                qualifies = turn <= self.MAX_TURN_RATE
            since = (previous["since"] if continuous and qualifies and previous["since"] is not None
                     else now if qualifies else None)
            current[ident] = {"at": now, "since": since,
                              "yaw": enemy.get("aim", [0])[0]}
        self.history = current  # Missing observations cannot retain a passer.

    def passer(self, enemy, me, now):
        record = self.history.get(enemy.get("id"))
        return bool(self.eligible and record and record["at"] == now
                    and record["since"] is not None
                    and now-record["since"] >= self.PASSER_SECONDS-1e-8
                    and self._conditions(enemy, me)
                    and abs(angle_error(enemy["aim"][0], record["yaw"])) < .001
                    and now-self.attacked_at.get(enemy["id"], -100) > self.ATTACK_MEMORY)

    def credible(self, obs, enemies):
        """Filter only a justified one-attacker encounter; otherwise keep all.

        Returned objects and order are unchanged. Full observed/memory threat
        lists must continue to feed cover, locomotion and emergency safety.
        """
        self.update(obs)
        enemies = list(enemies)
        self.ignored = set()
        if not self.eligible or len(enemies) < 2:
            return enemies
        credible = [e for e in enemies if not self.passer(e, obs["self"], obs["t"])]
        if len(credible) != 1:
            self.reason = "no justified single-attacker interpretation"
            return enemies
        self.ignored = {e["id"] for e in enemies if e["id"] != credible[0]["id"]}
        self.reason = "one credible attacker; sustained distant passers"
        return credible
