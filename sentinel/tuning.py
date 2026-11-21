"""Strategy preferences, not physics. Physics always comes from hello.config.

These are starting hypotheses. Change them using scored practice evidence.
"""

GRID_STEP = 6.0                 # meters; the ground route planner's resolution
PLAN_SECONDS = 0.009            # leave most of the 50 ms budget for I/O and tactics
PLAN_EXPANSIONS = 1400          # also bounds work on faster computers
GOAL_INTERVAL = 1.2             # avoid thrashing between equally good hiding places
RETREAT_HP = 0.65               # stop optional fights to let regeneration start
ENERGY_RESERVE = 26.0           # retain an emergency sprint / jet budget
THREAT_MEMORY = 12.0            # seconds; only previously observed enemies
PREFERRED_DISTANCE = 105.0      # gun range is longer; lightning is much shorter

# Escape speed and recovery help both practice (a hostile squad) and the final.
UPGRADE_VALUE = {
    "servos": 100, "nanites": 97, "armor": 91, "plating": 87,
    "reactor": 80, "jets": 77, "capacitor": 68, "gun_damage": 65,
    "gun_rate": 64, "gun_mag": 63, "laser_charge": 62,
    "laser_damage": 60, "lightning_range": 59, "gun_velocity": 57,
    "gyros": 52, "lightning_efficiency": 50, "sensors": 43,
    "mortar_reload": 42, "mortar_splash": 39, "mortar_velocity": 37,
    "lightning_chain": 30, "laser_pierce": 20,
}
