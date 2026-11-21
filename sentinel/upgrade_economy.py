"""A limited correction to early gun and sheltered-repair upgrade choices.

Effects come from hello.config; descriptions are never interpreted. Ordinary
priorities remain the fallback, including secondary builds and urgent movement.
Weapon capacity is not treated as instant ammunition or immediate healing.
"""
import math

from .geometry import distance
from .tuning import UPGRADE_VALUE


class UpgradeEconomy:
    def __init__(self, config, fallback_values=None):
        self.config = config
        self.definitions = {u["id"]: u for u in config.get("upgrades", ())}
        self.fallback = dict(UPGRADE_VALUE if fallback_values is None else fallback_values)
        self.reason = "ordinary upgrade priorities"
        self.comparison = {}

    def weapon_after(self, stats, upgrade_id, kind="gun"):
        result = dict(stats)
        prefix = "weapons."+kind+"."
        for effect in self.definitions.get(upgrade_id, {}).get("effects", ()):
            if effect["path"].startswith(prefix):
                key = effect["path"][len(prefix):]
                if key in result:
                    result[key] = result[key]*effect.get("mul", 1)+effect.get("add", 0)
        return result

    @staticmethod
    def cyclic_dps(stats):
        """Analytic reference, not an assertion about tick/reload ordering."""
        return stats["damage"]*stats["mag"]/max(.001, stats["mag"]*stats["cooldown"]+stats["reload"])

    @staticmethod
    def finish_time(weapon, stats, hp):
        """Ideal current-ammo clock with reload overlap and decision allowance.

        The comparison conservatively keeps current ammo and timers; the
        protocol promises no instant refill. New capacity is used at a later
        reload. Hit probability and travel are excluded from this firing clock.
        """
        shots = max(1, math.ceil(max(0, hp)/max(.001, stats["damage"])))
        magazine = max(1, int(stats["mag"]))
        reload_left = weapon.get("reload", 0)
        if reload_left > 0:
            at, ammo = max(reload_left, weapon.get("cooldown", 0)), magazine
        elif weapon.get("ammo", 0) <= 0:
            at, ammo = stats["reload"], magazine
        else:
            at, ammo = weapon.get("cooldown", 0), min(magazine, int(weapon["ammo"]))
        if shots <= ammo:
            return at+(shots-1)*stats["cooldown"]
        at += (ammo-1)*stats["cooldown"]+.1+stats["reload"]
        shots -= ammo
        full = (shots-1)//magazine
        at += full*((magazine-1)*stats["cooldown"]+.1+stats["reload"])
        shots -= full*magazine
        return at+(shots-1)*stats["cooldown"]

    def fresh_repair(self, me, seconds, upgrade_id=None):
        """HP restored after a NEW quiet interval; never assume quiet already."""
        if not me.get("in_zone", True):
            return 0
        rate = me["stats"]["regen_per_s"]
        delay = me["stats"]["regen_delay"]
        for effect in self.definitions.get(upgrade_id, {}).get("effects", ()):
            if effect["path"] == "mech.regen_per_s":
                rate = rate*effect.get("mul", 1)+effect.get("add", 0)
            elif effect["path"] == "mech.regen_delay":
                delay = delay*effect.get("mul", 1)+effect.get("add", 0)
        return min(max(0, me["max_hp"]-me["hp"]), max(0, seconds-max(0, delay))*rate)

    def _urgent_zone(self, obs):
        me = obs["self"]
        if not me.get("in_zone", True):
            return True
        zone = obs.get("zone")
        if zone is None:
            return False
        now = obs["t"]
        start = max(now, zone["shrink_start"])
        f = min(1, max(0, now+8-start)/max(.001, zone["shrink_end"]-start))
        center = [zone["center"][i]+f*(zone["next_center"][i]-zone["center"][i]) for i in range(2)]
        radius = zone["radius"]+f*(zone["next_radius"]-zone["radius"])
        return distance(me["pos"], center)+me["stats"]["radius"]+9 >= radius

    def choose(self, obs, *, target=None, recovering=False, sheltered=False):
        offer = obs.get("offer")
        choices = offer.get("choices", ()) if offer else ()
        self.comparison = {}
        if not choices:
            self.reason = "no offered choice"
            return None
        ordinary = max(range(len(choices)), key=lambda i: self.fallback.get(choices[i].get("id"), 0))
        if offer.get("expires", math.inf) <= obs["t"]:
            self.reason = "expired offer uses documented default choice zero"
            return 0
        me = obs["self"]
        ids = {choice.get("id"): i for i, choice in enumerate(choices)}
        if self._urgent_zone(obs):
            self.reason = "preserve ordinary mobility and storm priorities"
            return ordinary
        hurt_now = any(e.get("type") == "damaged" and e.get("amount", 0) > 0 for e in obs.get("events", ()))
        if ("nanites" in ids and recovering and sheltered and not hurt_now
                and me.get("upgrades", []).count("nanites") < self.definitions.get("nanites", {}).get("max", 0)):
            before, after = self.fresh_repair(me, 5), self.fresh_repair(me, 5, "nanites")
            self.comparison.update(repair_5s_before=before, repair_5s_after=after)
            if after-before >= self.config["weapons"]["gun"]["damage"]:
                self.reason = "nanites restore at least one extra gun hit in a real five-second shelter window"
                return ids["nanites"]
        gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
        second = next((w for w in me["weapons"] if w and w["kind"] != "gun"), None)
        uncommitted_pressure = target is None and any(
            e.get("kind") == "mech" and distance(me["pos"], e["pos"]) < 185
            for e in obs.get("mechs", ()))
        if (gun is None or second is not None or "gun_mag" not in ids or obs["t"] > 120
                or obs.get("alive", 16) <= 8 or me["hp"] < .40*me["max_hp"]
                or target is not None and target.get("charging")
                or me["energy"] < 26 or uncommitted_pressure):
            self.reason = "preserve ordinary defense, mobility or secondary-build choices"
            return ordinary
        offered = [ident for ident in ("gun_mag", "gun_damage", "gun_rate") if ident in ids and ident in self.definitions]
        if "gun_mag" not in offered:
            return ordinary
        stats = gun["stats"]
        projected = {ident: self.weapon_after(stats, ident) for ident in offered}
        before = self.cyclic_dps(stats)
        gains = {ident: self.cyclic_dps(after)/before-1 for ident, after in projected.items()}
        self.comparison.update(cyclic_dps_before=before, cyclic_gains=gains,
                               current_ammo=gun.get("ammo", 0), current_mag=stats["mag"])
        if target is not None and target.get("kind") == "mech" and target.get("hp", 0) > 0:
            times = {ident: self.finish_time(gun, after, target["hp"]) for ident, after in projected.items()}
            best = min(offered, key=lambda ident: (times[ident], -gains[ident]))
            base_time = self.finish_time(gun, stats, target["hp"])
            self.comparison.update(firing_times=times, firing_time_before=base_time)
            if best == "gun_mag" and base_time-times[best] >= .1:
                self.reason = "drum gives the best current-ammo finish clock without inventing a refill"
                return ids[best]
        elif (me.get("upgrades", []).count("gun_mag") == 0
              and gains["gun_mag"] > max([.15, *(g for ident, g in gains.items() if ident != "gun_mag")])):
            self.reason = "first drum beats offered gun alternatives on early sustained throughput"
            return ids["gun_mag"]
        self.reason = "no demonstrated drum or repair advantage; preserve ordinary priorities"
        return ordinary
