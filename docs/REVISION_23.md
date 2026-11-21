# Revision 23 repairs between committed duels

The 4.04 controller takes more fights to completion. After a confirmed kill,
its ordinary target selection can resume firing at a crate before health
regenerates. A crate hit resets the repair clock even when there are no
incoming shots. The refit couples the more committed duels with a short
recovery period between engagements.

The refit starts with missing health or a thin magazine. It keeps verified
kill salvage, suppresses optional fire, and rearms only once cover or a quiet
field makes a partial reload safe. It ends at 90% health and a gun at least
65% loaded, subject to a fixed deadline of at most 18 seconds. Imminent new
pressure, hostile damage, or storm risk restores ordinary movement and combat.
A committed duel cannot override an active refit.

In the 20 Hz test, a projectile kills a wounded mech before both policies
receive the same two-cube reward. At 11 seconds, the refit has 1,298.75 HP and
12 gun rounds. The 4.04 controller has 1,147.75 HP and 12 rounds after spending
seven shots to collect another cube and a lightning pickup. The refit gains
151 current HP for giving up that reward. With a 90 HP crate, the gain falls
to 2.5 HP. An incoming shot from an approaching hunter ends the refit within
one observation of the hunter appearing.

All 144 local tests passed. The official checker answered 300/300 on time,
with a 6.5 ms maximum. The crowded and growing-body benchmarks had maxima
of 21.32 and 13.66 ms.
