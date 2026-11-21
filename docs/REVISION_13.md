# Revision 13: collect verified kill rewards before the next fight

The 3.63 controller excludes cube objectives while recovering and when a known
threat is within 95 m. This can leave the reward from a won fight on the ground
as the next hunter arrives. Two cubes from an opponent with none immediately
grant 112 HP, 8% more maximum HP and damage, and the first upgrade offer under
the default rules. Larger bundles can cross multiple upgrade thresholds.

When the server confirms a kill, the bot briefly remembers the victim's last
observed location. It uses that location to associate actual cube observations
with the fight. It starts a short ground route only if it can arrive before a
nearby enemy, stay inside the predicted circle, and retain enough energy and HP
after estimated incoming rounds and weapons. It checks that a larger mech can
still fit through the corridor after pickup. The route is reevaluated each
decision and immediately yields to an emergency or a losing pickup race.

Salvage uses the 3.63 movement and combat controller. It adds a bounded route
priority only after a confirmed kill. It can cross open ground when the arrival
and damage budgets support the pickup. The target must be associated with an
actual cube ID. No cube positions or rewards are inferred from unseen drops.

In independent 20 Hz ground feedback, an actual simulated kill leaves a cube
bundle during the arrival of an armed pursuer. The previous bot collects none.
The new controller collects five cubes at 1.80 s and ends the three-second
case with 660 HP versus 515, plus a larger health pool and better gun damage.
In a two-cube case it collects both at 1.50 s and ends with 447 HP versus 515.
Taking a small bundle can spend more immediate HP than the cubes restore. The
losing-race, narrow-growth, and urgent-zone scenarios all reject salvage. These
models exercise timing and costs in controlled setups. House behavior, complete
weapon mechanics, and placement are evaluated by the scored practice service.

The canonical local checks passed all 98 tests, including 13 policy cases and
five physical feedback cases. The official checker returned 300/300 on-time
answers with a maximum of 8.7 ms. Crowded and growing-body synthetic host
timing peaked at 21.31 and 20.88 ms, respectively.
