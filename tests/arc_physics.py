"""Public20Hz ground acceleration, energy and charge movement penalty."""
import math


def move(me, action, world, charging=False):
    stats = me["stats"]
    command = action.get("move", [0, 0])
    length = max(1, math.hypot(*command))
    boost = action.get("boost", False) and me["energy"] >= stats["boost_drain"]*.05
    speed = stats["boost_speed"] if boost else stats["walk_speed"]
    if charging:
        speed *= stats["charge_move_mult"]
    wanted = [command[i]/length*speed for i in range(2)]
    delta = [wanted[i]-me["vel"][i] for i in range(2)]
    fraction = min(1, stats["ground_accel"]*.05/max(1e-12, math.hypot(*delta)))
    me["vel"] = [me["vel"][i]+delta[i]*fraction for i in range(2)]+[0]
    proposed = [me["pos"][i]+me["vel"][i]*.05 for i in range(2)]
    proposed.append(world.ground(*proposed))
    clear = world.walk_clear(me["pos"], proposed, stats["radius"], stats["height"], stats["step_up"])
    if clear:
        me["pos"] = proposed
    else:
        me["vel"] = [0, 0, 0]
    if boost and math.hypot(*command) > 0:
        me["energy"] -= stats["boost_drain"]*.05
        me["_quiet"] = 0
    else:
        me["_quiet"] = me.get("_quiet", 100)+.05
        if me["_quiet"] >= stats["energy_regen_delay"]:
            me["energy"] = min(stats["energy"], me["energy"]+stats["energy_regen"]*.05)
    return clear
