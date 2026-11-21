# Revision 21 reaches an announced supply drop in time to capture it

The 3.75 controller only targets a drop less than 150 m away with less
than eight seconds left to land. A drop can be reported 25 seconds before
landing. Walking farther than 150 m takes over 12 seconds, even on open
ground, leaving some useful repair opportunities outside the old gate.

This controller uses that announcement to plan an intact ground route.
It delays departure when a nearby drop would otherwise leave it waiting
in the open. It budgets sprint energy for longer approaches and checks
each route segment against the storm at the expected arrival time. The
mech brakes inside the landing ring and uses the server's capture clock.
An enemy that can contest a near-term capture, an unsafe route, or a
stalled server clock returns control to ordinary movement. The approach
uses the gun to avoid a laser charge halving movement speed.

With a real announcement at 70 s and a drop 300 m away, the baseline's
goal selection excludes the drop. In the controlled ground model, the
integrated controller arrives and holds through the full four-second
clock at 99.00 s. Its minimum energy is 83. That scenario is unopposed.
The first possible capture occurs around 99 s, so this revision can only
affect matches that last that long.

All 137 local tests passed, including the route and capture cases.
The official checker answered 300/300 on time, with maximum 8.5 ms.
The crowded and growing-body maxima were 21.27 and 21.55 ms.
