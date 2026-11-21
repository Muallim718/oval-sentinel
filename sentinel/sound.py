"""Anonymous offensive sounds request a bounded look, never a world target.

The strategy calls heading only when real combat and known danger have no aim.
Repeated bearings stabilize and extend a look; a distant unobservable shooter
cannot monopolize quiet scanning indefinitely.
"""
import math

from .geometry import angle_error


class SoundScout:
    KINDS = frozenset(("gun", "mortar", "laser", "laser_charge", "lightning", "npc_gun"))
    MAX_CLUSTERS = 8
    MAX_SOUND_AGE = .35
    CLUSTER_ANGLE = math.radians(22)
    CLUSTER_TTL = 2.0
    MAX_WATCH = 1.6
    REARM_SECONDS = 1.0

    def __init__(self, config):
        turn = max(.5, config["mech"].get("turn_rate", 4))
        half_fov = math.radians(config.get("vision", {}).get("fov_deg", 120))*.5
        noise = math.radians(config.get("sound", {}).get("bearing_noise_deg", 7))
        self.covered_angle = max(0, half_fov-max(self.CLUSTER_ANGLE, noise*2))
        # A single cue must last long enough to turn even a rear contact into
        # the real field of view. Confirmation extends this, not the first look.
        self.initial_watch = min(1.1, max(.6, (math.pi-half_fov)/turn+.2))
        self.clusters = []
        self.active = None
        self.sequence = 0
        self.last_observation = None
        self.state, self.reason = "idle", "no recent offensive sound"

    def _priority(self, cluster):
        return (cluster["charge"], cluster["band"], min(2, cluster["samples"]), cluster["last"])

    def update(self, obs):
        now = obs["t"]
        key = (obs.get("tick"), now)
        if key == self.last_observation:
            return
        self.last_observation = key
        self.clusters = [c for c in self.clusters if now-c["last"] <= self.CLUSTER_TTL]
        if self.active not in self.clusters:
            self.active = None
        sounds = [s for s in obs.get("sounds", ()) if s.get("kind") in self.KINDS
                  and isinstance(s.get("bearing"), (int, float))
                  and math.isfinite(s["bearing"])
                  and 0 <= s.get("age", 0) <= self.MAX_SOUND_AGE]
        sounds.sort(key=lambda s: -s.get("age", 0))
        for sound in sounds:
            event_at = now-sound.get("age", 0)
            bearing = angle_error(sound["bearing"], 0)
            choices = [c for c in self.clusters if event_at >= c["last"]-.001
                       and event_at-c["last"] <= .8
                       and abs(angle_error(bearing, c["yaw"])) <= self.CLUSTER_ANGLE]
            cluster = min(choices, key=lambda c: abs(angle_error(bearing, c["yaw"])), default=None)
            band = {"near": 3, "mid": 2, "far": 1}.get(sound.get("dist"), 0)
            charge = sound["kind"] == "laser_charge"
            if cluster is None:
                self.sequence += 1
                cluster = {"id": self.sequence, "yaw": bearing, "last": event_at,
                           "samples": 1, "band": band, "charge": charge,
                           "start": None, "until": -1, "rearm": -1}
                self.clusters.append(cluster)
            elif event_at-cluster["last"] >= .07:
                # Circular averaging handles bearings straddling -pi/+pi.
                weight = min(4, cluster["samples"])
                cluster["yaw"] = math.atan2(math.sin(cluster["yaw"])*weight+math.sin(bearing),
                                            math.cos(cluster["yaw"])*weight+math.cos(bearing))
                cluster["samples"] += 1
                cluster["last"], cluster["band"], cluster["charge"] = event_at, band, charge
                if cluster is self.active and cluster["start"] is not None:
                    cluster["until"] = min(cluster["start"]+self.MAX_WATCH, now+self.initial_watch)
            else:
                # Simultaneous cues can upgrade urgency but never manufacture
                # temporal confirmation from one observation.
                cluster["band"] = max(cluster["band"], band)
                cluster["charge"] |= charge
            if len(self.clusters) > self.MAX_CLUSTERS:
                removable = [c for c in self.clusters if c is not self.active]
                old = min(removable, key=self._priority)
                self.clusters.remove(old)
        actual = obs.get("self", {}).get("aim")
        if actual is not None:
            for cluster in self.clusters:
                if abs(angle_error(cluster["yaw"], actual[0])) <= self.covered_angle:
                    # The latest real observation has already looked at this
                    # whole bearing cone. Centering an unseen/occluded source
                    # reveals nothing extra because visibility is a yaw wedge.
                    # Real targets already take aim priority in the caller.
                    cluster["rearm"] = max(cluster["rearm"], now+self.REARM_SECONDS)
                    cluster["start"], cluster["until"] = None, -1
                    if cluster is self.active:
                        self.active = None

    def heading(self, now):
        """Return only a yaw request. Real target and damage aim take priority."""
        if self.active is not None and now >= self.active["until"]:
            self.active["rearm"] = now+self.REARM_SECONDS
            self.active["start"] = None
            self.active = None
        available = [c for c in self.clusters
                     if now-c["last"] <= self.MAX_SOUND_AGE and now >= c["rearm"]]
        best = max(available, key=self._priority, default=None)
        # Do not swing back and forth between equally urgent anonymous shots.
        # A closer band or a prefire charge can interrupt the current look.
        higher = (best is not None and self.active is not None and
                  (best["charge"], best["band"]) > (self.active["charge"], self.active["band"]))
        if self.active is None and best is not None or higher:
            self.active = best
            best["start"] = now
            best["until"] = now+self.initial_watch
        if self.active is None:
            self.state, self.reason = "idle", "offensive cue expired; resume ordinary scan"
            return None
        self.state = "watch"
        self.reason = "turn toward anonymous offensive sound"
        return self.active["yaw"]
