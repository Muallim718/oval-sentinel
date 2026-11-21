"""Sustain fire through the early isolated fights that award placement."""
from dataclasses import dataclass
import math

from .combat import target_center
from .geometry import angle_error, distance


@dataclass(frozen=True)
class CommittedDuel:
    enemy: dict
    range: float
    sprint: bool


class DuelCommitment:
    def __init__(self, config):
        self.config = config
        self.damage_sources = {}
        self.target_id = None

    def _lane(self, world, me, enemy):
        origin = (me["pos"][0], me["pos"][1], me["pos"][2]+me["stats"]["muzzle_height"])
        target, _, height = target_center(enemy, self.config)
        return (world.line_clear(origin, target) or world.line_clear(
                origin, (target[0], target[1], target[2]+.4*height)))

    def _crossfire(self, world, me, target, threats):
        p = me["pos"]
        for enemy, confidence in threats:
            if enemy["id"] == target["id"] or confidence < .45:
                continue
            d = distance(p, enemy["pos"])
            if d >= 185 or not self._lane(world, me, enemy):
                continue
            bearing = math.atan2(p[1]-enemy["pos"][1], p[0]-enemy["pos"][0])
            if d < 88 or enemy.get("charging") or abs(angle_error(bearing, enemy["aim"][0])) < .70:
                return True
        return False

    def choose(self, obs, threats, circle, world, *, sheltered=False):
        me, now = obs["self"], obs["t"]
        self.damage_sources = {source: at for source, at in self.damage_sources.items() if now-at < 1.5}
        for event in obs["events"]:
            if event["type"] == "damaged" and event.get("weapon") not in ("zone", "npc"):
                self.damage_sources[event.get("by")] = now
        if sheltered or obs["alive"] <= 8 or not me["in_zone"] or not me["grounded"]:
            self.target_id = None
            return None
        if distance(me["pos"], circle[0])+9 >= circle[1]:
            self.target_id = None
            return None
        weapons = {weapon["kind"]: weapon for weapon in me["weapons"] if weapon}
        gun = weapons.get("gun")
        if gun is None:
            self.target_id = None
            return None
        reach = min(180, gun["stats"]["range"]-12)
        candidates = [enemy for enemy in obs["mechs"] if enemy["kind"] == "mech" and
                      distance(me["pos"], enemy["pos"]) < reach and self._lane(world, me, enemy)]
        if not candidates:
            self.target_id = None
            return None
        enemy = min(candidates, key=lambda item: (distance(me["pos"], item["pos"])-
                    (24 if item["id"] == self.target_id else 0)))
        enemy_hp = enemy.get("hp", enemy.get("max_hp", 1400))
        ratio = me["hp"]/me["max_hp"]
        finish = ratio >= .23 and enemy_hp < min(520, .68*me["hp"])
        # Continue an even contest below the ordinary 70% duel threshold. A
        # briefly favorable finish can also justify staying below 58% health.
        stays = ratio >= (.47 if self.target_id == enemy["id"] else .57) and enemy_hp < me["hp"]*1.30
        if ((not finish and not stays) or self._crossfire(world, me, enemy, threats) or
                any(source is not None and source != enemy["id"] for source in self.damage_sources)):
            self.target_id = None
            return None
        d = distance(me["pos"], enemy["pos"])
        enemy_weapons = enemy.get("weapons", ())
        arc, laser, mortar = (weapons.get(kind) for kind in ("lightning", "laser", "mortar"))
        desired = 42.0
        if arc and me["energy"] >= arc["stats"]["energy"]*6+25:
            desired = .70*arc["stats"]["range"]
        elif "lightning" in enemy_weapons:
            desired = 64.0
        elif laser and "mortar" in enemy_weapons:
            desired = 109.0
        elif mortar and not laser:
            desired = 48.0

        loaded = gun.get("reload", 0) <= 0 and gun.get("ammo", 0) >= 4
        move_in = d > desired+22 and me["energy"] >= 64 and loaded
        if laser and laser.get("charge", 0) > 0:
            move_in = False
        if not loaded and not (laser or arc or mortar) and d < 34 and not finish:
            # Let the original movement seek protection during an empty-mag gap.
            self.target_id = None
            return None
        self.target_id = enemy["id"]
        return CommittedDuel(enemy, desired, move_in)
