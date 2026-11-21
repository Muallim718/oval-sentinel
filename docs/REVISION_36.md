# Revision 36 sustained combat against confirmed attackers

The 4.04 controller closes most early gun fights to 42 m and reverts to
ordinary recovery when the engagement becomes less favorable. A gun shot
from that range can arrive before a reactive boost moves the mech away.
This candidate changes how the parts of the fight work together.

It uses the confirmed-attacker filter to avoid opening unnecessary fights.
It keeps a clear isolated engagement at lower health when an opponent is
already pressing, including beyond the first eight kills. A gun fight aims
for about 76 m where the available space allows it, with the existing special
ranges for secondary weapons. The real visible-round dodge can then spend a
short burst of boost on a path that avoids contact. Crossfire, useful sheltered
repair, and zone urgency still take priority.

All 141 local tests passed. The official checker answered 300/300 on time,
with an 8.2 ms maximum. Crowded and growing-body maxima were 22.05 and
32.34 ms.
