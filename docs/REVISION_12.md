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

| Local cases | 3.63 baseline | Duel controller |
| --- | ---: | ---: |
| Equal-loadout kills, 48 cases | 47 | 48 |
| Equal-loadout mean remaining HP | 548 | 748 |
| Equal-loadout mean damage taken | 853 | 652 |
| Stronger-opponent kills, 8 cases | 5 | 7 |
| Stronger-opponent mean remaining HP | 358 | 545 |

Remaining HP improved in 40 of 48 equal-loadout cases, held in four, and fell
in four. Each opponent style improved on average under both firing orders.
The motion-only comparison finished with 46 kills and 555 mean HP, so the
complete duel policy produced the larger gain. The stronger-opponent set uses
three cubes on the opponent, increasing its HP, damage, and size using public
scaling rules. All runs stayed inside the modeled zone and used ground movement.

The tested commit `dcf766ee63baa849d428fec959136f83668713b5` passed all 107 tests
on Linux and built the pinned image. The official restricted-container check
answered 300/300 on time, with p99 10.0 ms and a 13.7 ms maximum. Linux host
crowded and growing-body maxima were 41.81 and 22.24 ms. The committed tree
was 2,296,606 bytes. [Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44935508466)

The practice service accepted the exact commit at 1:27 PM EST on November 21,
2026, under receipt `BB-38741C93`. It scored **3.38**, 0.25 below the selected
3.63 entry. The synthetic duel gains did not translate to scored placement.
The service provides an aggregate score, so the cause of the decline is unknown.
The runtime remains on the [duel-control experiment branch](https://github.com/Muallim718/oval-sentinel/tree/experiment/duel-control).
