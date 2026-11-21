"""Weapon operating envelopes and energy-feasible isolated-duel sprints.

This does not decide whether a duel is favorable or whether a shot can hit.
The caller retains HP, cover, zone, aiming, and actual movement safety checks.
"""
import math
from .geometry import distance, unit


ENERGY_RESERVE = 30.0


def _cube_damage(me, config):
    cubes = min(me.get("cubes", 0), config["cubes"].get("stat_cap", 10))
    return 1+config["cubes"].get("damage_per_cube", .04)*cubes


def _gun_dps(me, config):
    gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
    if gun is None or gun.get("ammo", 0) <= 0 or gun.get("reload", 0) > .5:
        return 0.0
    stats = gun["stats"]
    cycle = stats["mag"]*stats["cooldown"]+stats["reload"]
    return stats["damage"]*stats["mag"]/(cycle or 1)*_cube_damage(me, config)


def _escape_sprint(me, enemy, preferred):
    if preferred < 70 or distance(me["pos"], enemy["pos"]) >= min(75, preferred-15):
        return False
    stats = me["stats"]
    charged = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])
    mobility = stats.get("charge_move_mult", .5) if charged else 1.0
    away = unit(me["pos"][0]-enemy["pos"][0], me["pos"][1]-enemy["pos"][1])
    velocity = enemy.get("vel", [0, 0, 0])
    pursuer_speed = velocity[0]*away[0]+velocity[1]*away[1]
    if pursuer_speed < -1:
        return False  # Already separating; do not spend escape energy on it.
    advantage = stats["boost_speed"]*mobility-pursuer_speed
    seconds = min(3.0, max(0, me["energy"]-ENERGY_RESERVE)/stats["boost_drain"])
    # A meaningful gap needs time and actual projected speed advantage. A
    # charging laser cannot promise full-speed escape before it is released.
    return seconds >= 1.0 and advantage*seconds >= 7.0


def _closing_time(me, enemy, gap):
    """Bounded 20Hz straight-lunge estimate, including existing lateral inertia."""
    direction = unit(enemy["pos"][0]-me["pos"][0], enemy["pos"][1]-me["pos"][1])
    velocity = enemy.get("vel", [0, 0, 0])
    away = velocity[0]*direction[0]+velocity[1]*direction[1]
    vx, vy = me["vel"][:2]
    stats = me["stats"]
    acceleration = stats["ground_accel"] if me.get("grounded", True) else stats["air_accel"]
    for tick in range(1, 51):
        dx, dy = direction[0]*stats["boost_speed"]-vx, direction[1]*stats["boost_speed"]-vy
        fraction = min(1, acceleration*.05/max(1e-9, math.hypot(dx, dy)))
        vx, vy = vx+dx*fraction, vy+dy*fraction
        gap -= (vx*direction[0]+vy*direction[1]-away)*.05
        if gap <= 0:
            return tick*.05
    return math.inf


def duel_envelope(me, enemy, config):
    """Return (preferred horizontal range, sprint_for_spacing).

    Sprint may close a short, feasible lightning gap or widen a dangerous close
    gun/laser engagement. It never changes the caller's combat eligibility.
    """
    gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
    gun_stats = gun["stats"] if gun else config["weapons"]["gun"]
    gun_range = min(gun_stats["range"]*.8, max(95.0, min(110.0, gun_stats["speed"]*.42)))
    preferred = gun_range
    enemy_kinds = enemy.get("weapons", ["gun"])
    second = next((w for w in me["weapons"] if w and w["kind"] != "gun"), None)
    d = distance(me["pos"], enemy["pos"])
    if second and second["kind"] == "laser":
        desired = 145.0 if "mortar" in enemy_kinds else (125.0 if "lightning" in enemy_kinds else 115.0)
        preferred = min(desired, second["stats"]["range"]*.8)
    elif second and second["kind"] == "mortar":
        preferred = 115.0 if "laser" in enemy_kinds else (75.0 if "lightning" in enemy_kinds else 85.0)
    elif second and second["kind"] == "lightning":
        stats = second["stats"]
        arc_range = stats["range"]
        operating = max(10.0, arc_range-6.0)
        damage = stats["damage"]*_cube_damage(me, config)
        one_hit = enemy.get("hp", 1400) <= damage
        usable = me["energy"] > stats["energy"]+8 and (one_hit or me["energy"] >= stats["energy"]*2+8)
        if usable and d <= arc_range:
            return operating, False  # Already able to arc; do not waste sprint energy.
        if usable and "mortar" not in enemy_kinds and me["hp"] >= me["max_hp"]*.90:
            gap = max(0, d-(arc_range-3))
            eta = _closing_time(me, enemy, gap)
            per_interval = damage+_gun_dps(me, config)*stats["cooldown"]
            shots = math.ceil(enemy.get("hp", 1400)/max(1, per_interval))
            # Reserve a useful initial burst, not the entire hypothetical kill.
            # Gun fire continues while approaching; demanding all winning arcs
            # upfront previously rejected a safe70m lunge and flipped midclose.
            firing_energy = min(8, shots)*stats["energy"]
            available = me["energy"]-ENERGY_RESERVE-firing_energy
            ready = second.get("cooldown", 0) <= max(.35, stats["cooldown"]+.05)
            if ready and 0 < eta <= 2.5 and eta*me["stats"]["boost_drain"] <= available:
                return operating, True
    return preferred, _escape_sprint(me, enemy, preferred)
