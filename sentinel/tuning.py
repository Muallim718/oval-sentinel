"""Strategy preferences, not physics. Physics always comes from hello.config.

These are starting hypotheses. Change them using scored practice evidence.
"""

GRID_STEP = 6.0                 # meters; the ground route planner's resolution
PLAN_SECONDS = 0.009            # leave most of the 50 ms budget for I/O and tactics
PLAN_EXPANSIONS = 1400          # also bounds work on faster computers
GOAL_INTERVAL = 1.2             # avoid thrashing between equally good hiding places
RETREAT_HP = 0.58               # enter recovery; remain there until 90% HP
ENERGY_RESERVE = 26.0           # retain an emergency sprint / jet budget
THREAT_MEMORY = 12.0            # seconds; only previously observed enemies
PREFERRED_DISTANCE = 75.0       # defensive distance; duels use weapon-specific ranges

# Escape speed and recovery help both practice (a hostile squad) and the final.
UPGRADE_VALUE = {
    "servos": 100, "nanites": 90, "armor": 94, "plating": 96,
    "reactor": 76, "jets": 72, "capacitor": 66, "gun_damage": 93,
    "gun_rate": 92, "gun_mag": 85, "laser_charge": 88,
    "laser_damage": 89, "lightning_range": 86, "gun_velocity": 65,
    "gyros": 52, "lightning_efficiency": 50, "sensors": 43,
    "mortar_reload": 42, "mortar_splash": 39, "mortar_velocity": 37,
    "lightning_chain": 30, "laser_pierce": 20,
}
