"""Choose an immediately useful gun finish before ranking weapon preferences.

The normal scheduler ranks target/weapon pairs. An available close-range weapon
must not erase a loaded, already-aligned short finish on another active attacker.
This module never moves, starts a chase, or predicts that an unobserved hit landed.
"""
from dataclasses import dataclass
import math

from .combat import Combat, target_center
from .geometry import angle_error, distance


@dataclass(frozen=True)
class FinishChoice:
    target: dict
    force_gun: bool
    shots: int
    seconds: float


class FinishTarget:
    MAX_SHOTS = 3
    MAX_SECONDS = 1.25

    def __init__(self, config):
        self.config = config
        armor = config["mech"].get("armor", 0)
        for upgrade in config.get("upgrades", ()):
            for _ in range(upgrade.get("max", 0)):
                for effect in upgrade.get("effects", ()):
                    if effect.get("path") == "mech.armor":
                        armor = armor*effect.get("mul", 1)+effect.get("add", 0)
        self.armor_bound = max(0, min(1, armor))
        self.reason = "ordinary target/weapon scheduler"
        self.choice = None
        self.target_id = None
        self.until = -100
        self.rejected = {}

    def _cancel(self, reason=None):
        self.target_id = None
        if reason:
            self.reason = reason
        return None

    def _body_blocks(self, obs, target, point, flight):
        origin = [*obs["self"]["pos"][:2], obs["self"]["pos"][2]+
                  obs["self"]["stats"]["muzzle_height"]]
        dx, dy = point[0]-origin[0], point[1]-origin[1]
        squared = dx*dx+dy*dy
        for other in [*obs["mechs"], *obs.get("crates", ())]:
            if other.get("id") == target["id"] or other.get("hp", 1) <= 0:
                continue
            center, radius, height = target_center(other, self.config)
            fraction = ((center[0]-origin[0])*dx+(center[1]-origin[1])*dy)/max(.001, squared)
            if not 0 < fraction < 1:
                continue
            velocity = other.get("vel", (0,0,0))
            px = center[0]+velocity[0]*flight*fraction
            py = center[1]+velocity[1]*flight*fraction
            fraction = ((px-origin[0])*dx+(py-origin[1])*dy)/max(.001, squared)
            if not 0 < fraction < 1:
                continue
            z = origin[2]+(point[2]-origin[2])*fraction
            bottom = other["pos"][2]+velocity[2]*flight*fraction
            if (bottom <= z <= bottom+height and math.hypot(
                    px-origin[0]-dx*fraction, py-origin[1]-dy*fraction) <= radius+.3):
                return True
        return False

    def choose(self, obs, targets, world, *, retreat=False, repairing=False, forced_weapon=None):
        self.choice, self.reason = None, "ordinary target/weapon scheduler"
        me, now = obs["self"], obs["t"]
        self.rejected = {ident: until for ident, until in self.rejected.items() if until > now}
        if self.target_id is not None and now >= self.until:
            self.rejected[self.target_id] = now+self.MAX_SECONDS
            self.target_id = None
        keeping = self.target_id is not None
        if retreat or repairing or forced_weapon or not me["in_zone"] or not me["grounded"]:
            return self._cancel("existing movement, repair or forced attack keeps priority")
        if any(w and w["kind"] == "laser" and w.get("charge", 0)>0 for w in me["weapons"]):
            return self._cancel("do not redirect or release an existing laser charge")
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        if not gun or gun.get("reload", 0)>0 or gun.get("ammo", 0)<=0:
            return self._cancel()
        if gun.get("cooldown", 0)>.10 and not keeping:
            return self._cancel()
        observed = {enemy["id"]: enemy for enemy in obs["mechs"] if enemy.get("kind") == "mech"}
        enemies = [observed[target["id"]] for target in targets
                   if target.get("kind") == "mech" and target["id"] in observed and target.get("hp", 0)>0]
        if len(enemies)<2 or len(obs["mechs"])+len(obs.get("crates", ()))>64:
            return self._cancel()
        events = [event for event in obs.get("events", ()) if event["type"] == "damaged" and
                  event.get("weapon") not in (None,"npc","zone")]
        if any(event.get("by") not in observed for event in events):
            return self._cancel("a new unseen attacker invalidates an optional finish")
        stats = gun["stats"]
        # Live gun damage is a conservative floor. Do not assume extra cube
        # scaling or a rear bonus; unknown enemy armor gets its public maximum.
        damage = stats["damage"]*(1-self.armor_bound)
        if damage <= 0:
            return self._cancel()
        solver = Combat(world, self.config)
        candidates = []
        for enemy in enemies[:8]:
            continuing = self.target_id == enemy["id"]
            if enemy["id"] in self.rejected or gun.get("cooldown", 0)>.10 and not continuing:
                continue
            if any(event.get("by") != enemy["id"] and
                   (event.get("rear") or event.get("weapon") in ("laser","mortar")) for event in events):
                continue
            shots = math.ceil(enemy["hp"]/damage)
            if shots > self.MAX_SHOTS or shots > gun.get("ammo", 0) and not continuing:
                continue
            solved = solver.solve(me, enemy, gun)
            if solved is None:
                continue
            aim, point, radius, height = solved
            d = max(1, distance(me["pos"], point))
            yaw_error = abs(angle_error(aim[0], me["aim"][0]))
            pitch_error = abs(aim[1]-me["aim"][1])
            yaw_tolerance = math.atan2(radius+.3, d)
            pitch_tolerance = math.atan2(height*.44, d)
            if continuing:
                # Once acquired, keep tracking through an ordinary cooldown.
                # Actual firing still uses Combat's current-torso hit test.
                yaw_tolerance = max(yaw_tolerance, me["stats"]["turn_rate"]*.10)
                pitch_tolerance = max(pitch_tolerance, me["stats"]["pitch_rate"]*.10)
            if yaw_error >= yaw_tolerance or pitch_error >= pitch_tolerance:
                continue
            origin = [*me["pos"][:2], me["pos"][2]+me["stats"]["muzzle_height"]]
            flight = math.dist(origin, point)/stats["speed"]
            slew = max(yaw_error/me["stats"]["turn_rate"],pitch_error/me["stats"]["pitch_rate"])
            seconds = max(slew, gun.get("cooldown", 0))+(shots-1)*stats["cooldown"]+flight+.10
            if seconds > self.MAX_SECONDS or self._body_blocks(obs, enemy, point, flight):
                continue
            candidates.append((not continuing, seconds, enemy["hp"], enemy["id"], enemy, shots))
        if not candidates:
            return self._cancel()
        _, seconds, _, _, enemy, shots = min(candidates)
        if self.target_id != enemy["id"]:
            self.target_id, self.until = enemy["id"], now+self.MAX_SECONDS
        force_gun = any(w and w["kind"] in ("laser","mortar") for w in me["weapons"])
        self.choice = FinishChoice(enemy, force_gun, shots, seconds)
        self.reason = "loaded aligned gun can finish an active attacker in a short burst"
        return self.choice
