# Revision 19 protects the recovery window after a kill

The 3.75 controller can start shooting a crate as soon as it wins a duel.
Every crate hit resets the five-second healing clock. This candidate keeps
collecting verified kill rewards while prioritizing health and ammunition
until the next hunter can intervene.

Only a confirmed kill of another mech can start the pause. The bot starts
when health or ammunition is low enough to benefit, and ends when health is
at least 90% and the gun is at least 65% loaded. A fixed deadline uses the
live repair and reload stats and caps the commitment at 18 seconds. A storm
deadline, nearby hunter, dangerous incoming shot, or damage from a fresh
attacker yields immediately to the ordinary controller. Severe damage keeps
using the ordinary recovery hysteresis. The pause suppresses optional shots
so healing can start, and enables a partial reload only in cover or when no
known opponent can interrupt it.

The controlled feedback case starts with a real gun projectile killing a
weakened mech. At 11 seconds, the baseline had 1,147.75 HP, 12 rounds, and
three cubes. It shot a crate seven times and earned its extra cube and a
lightning pickup. The refit had 1,298.75 HP, 12 rounds, and two cubes, with
no crate shots. Regeneration began at 4.9 seconds in the refit and at 9.5
seconds in the baseline. An incoming round from a hunter rounding a wall
ended the refit within one observation of that hunter appearing. This model
tests the healing and magazine tradeoff before the next engagement.

At three seconds the refit's partial reload had 0.15 seconds remaining, while
the baseline's reload had 0.45 seconds remaining. A case with a 90 HP crate gave the
refit only 2.5 more current HP at 11 seconds while the baseline kept the
extra cube and lightning. Cheap rewards can be worth taking immediately.

All 137 local tests passed. The official recording received 300 valid
on-time replies with an 8.5 ms maximum. Crowded and growing-body benchmarks
peaked at 11.47 and 22.45 ms respectively.
