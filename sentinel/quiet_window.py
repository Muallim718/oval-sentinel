"""Attack permission is independent of the route used to stay alive.

An escape route is not a healing opportunity. Silence belongs to a verified
refuge or health regeneration we have actually observed, rather than to a low
HP label.
"""
import math

from .geometry import angle_error, distance


class QuietWindow:
    def __init__(self, config):
        self.config = config
        self.last_incoming = self.last_dealt = -100.0
        self.healing_at = -100.0
        self.previous = None
        self.reason = None

    def update(self, obs):
        """Keep bounded public evidence; call once before mode selection."""
        now, me = obs["t"], obs["self"]
        for event in obs.get("events", ()):
            if event["type"] == "damaged":
                self.last_incoming = now
            elif event["type"] == "hit":
                self.last_dealt = now
        previous = self.previous
        delay = me["stats"].get("regen_delay", self.config["mech"].get("regen_delay", 5))
        if (previous is not None and me["in_zone"] and
                0 < now-previous[0] <= .25 and me["hp"] > previous[1]+.001 and
                me["max_hp"] == previous[2] and me.get("cubes", 0) == previous[3] and
                now-max(self.last_incoming, self.last_dealt) >= delay-.15):
            self.healing_at = now
        if now-max(self.last_incoming, self.last_dealt) < delay-.15:
            self.healing_at = -100.0
        self.previous = (now, me["hp"], me["max_hp"], me.get("cubes", 0))

    def _imminent(self, obs, sheltered=False):
        """Continuous closest approach; a fast round can cross between ticks."""
        me, stats = obs["self"], obs["self"]["stats"]
        pos, velocity = me["pos"], me.get("vel", (0, 0, 0))
        for projectile in obs.get("projectiles", ())[:24]:
            pp, pv = projectile["pos"], projectile["vel"]
            rx, ry = pp[0]-pos[0], pp[1]-pos[1]
            vx, vy = pv[0]-velocity[0], pv[1]-velocity[1]
            t = max(0., min(.65, -(rx*vx+ry*vy)/(vx*vx+vy*vy or 1)))
            radius = stats["radius"]+.6
            z = pp[2]+pv[2]*t
            if projectile["kind"] == "mortar":
                radius += self.config["weapons"]["mortar"]["splash_radius"]
                z -= self.config["weapons"]["mortar"]["gravity"]*t*t/2
            if math.hypot(rx+vx*t, ry+vy*t) < radius and pos[2]-2 < z < pos[2]+stats["height"]+2:
                return True
        for enemy in (() if sheltered else obs.get("mechs", ())):
            if enemy.get("kind") != "mech" or not enemy.get("charging"):
                continue
            d = distance(pos, enemy["pos"])
            bearing = math.atan2(pos[1]-enemy["pos"][1], pos[0]-enemy["pos"][0])
            if d < self.config["weapons"]["laser"]["range"] and abs(angle_error(bearing, enemy["aim"][0])) < .3:
                return True
        return False

    def repair(self, obs, *, sheltered):
        """Give repair priority when there is evidence of a quiet window.

        `sheltered` must describe the *current* grounded body against all known
        firing lanes, not a distant chosen cover goal. It comes from CoverPlanner.
        """
        now = obs["t"]
        protected = sheltered and now-self.last_incoming > .5
        regenerating = now-self.healing_at <= .2
        self.reason = None
        if obs["self"]["in_zone"] and (protected or regenerating) and not self._imminent(obs, sheltered):
            self.reason = "verified shelter" if protected else "observed regeneration"
        return self.reason is not None
