# Revision 12: gunfight movement and firing windows

The 3.63 baseline can find shelter and recover behind a wall. In an open duel,
it estimates projectile risk using a single average velocity for each movement
command. A lead shot can intercept the mech while it is still accelerating or
reversing. In addition, the trigger checks use aim from the observation even
when the same action commands a different aim. On the next simulation tick the
torso may already have turned away from the shot the check approved.

These are concrete control problems. The practice service reports a mean score,
so we cannot tell how often they caused a loss in the 48 scored matches.

The experiment checks incoming rounds against the same 50 ms acceleration
samples used to see where each evasive command would move the mech. It ranks
rounds by when they can enter the reachable area, checks the vertical hit
interval, and discards straight rounds stopped by walls. The search compares a
fixed number of commands against at most eight inbound rounds. In a suitable
open duel, lateral speed changes make it harder to lead a steady strafe.

Gun and laser aim accounts for relative motion before the shot. The trigger
checks the shared torso angle at both plausible ends of the 50 ms firing step.
The commanded aim tracks the later end so that the next observation does not
start with stale tracking. A 20 Hz feedback case with two opposing sprinters
caught a problem with aiming at the midpoint: over 100 decision frames it
usually withheld the gun while tracking a target that remained hittable.

The spacing policy uses roughly 106 m for the starting gun. That gives a
252 m/s bullet about 0.4 s of flight, making a late turn or brake useful. The
bot can sprint away from a close pursuer if the projected speed advantage buys
separation. It closes for lightning only if the mech can reach arc range with
enough energy for an opening burst and a 30-energy reserve. Laser and mortar
set their own range based on the opponent's loadout. The existing mode checks
still decide when a duel is favorable and when to abort for crossfire or damage.

Local verification passed 107 tests and the official 300-observation check.
All 300 replies were on time, with no protocol errors and a 4.9 ms maximum.
Local crowded and growing-body benchmarks peaked at 12.62 and 23.47 ms.

The optional `tools/duel_lab.py` runs the same reactive gun-duel cases on any
checkout via `--project-dir`. Run with `--ranges 50 90 140 190 --seeds 11 29 47`
for 48 equal-loadout cases. Add `--ranges 90 --seeds 71 103 --enemy-cubes 3`
for eight separate cases with a stronger pursuer or kiter. Both sets use a
static arena and two plausible weapon-tick orders. They omit actual house AI,
secondary combat, loot, and match progression. They measure damage and HP in
controlled fights. Placement is measured by scored practice.
