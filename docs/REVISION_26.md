# Revision 26 uses more of the time available in early fights

The selected 4.04 controller finishes more isolated fights. It can still
lose time locating the attacker, get stuck aiming a ready mortar, or spend
the gun's reload in an enemy firing lane. This revision addresses those
gaps while retaining the committed fight and ordinary recovery decisions.

When quiet, the torso can investigate a fresh sound. Gun and laser solutions
can use a physically exposed part of the target when the center ray hits
cover. This part of the revision previously scored 3.96 on a 3.75 base.
The same public bearings and observed bodies are used here.
[Contact acquisition test and practice result](REVISION_17.md)

A mortar that cannot pass its original angular gate can fire after a trace
verifies safe contact under multiple firing orders. After three unproved
ready decisions, the gun gets a short window if it has a shot at the same
target. In the sprinting feedback case, the old controller fired neither
weapon and the new one lands three to six physical gun hits. At ordinary
walk speed and 30 m it also lands a direct 360 damage shell in both orders.

During a gun reload the bot can collect a real nearby weapon on a short,
verified route and keep its existing aim and triggers. The actual equipment
cooldown still applies. In the shared-reload test, the new laser and lightning
routes reduce time to first kill from 10.35 s to 5.40 and 4.40 s, and leave
460 and 595 HP at first kill compared with 55 for the baseline.
[Test conditions and reproduction](ARMING_LAB.md)

When there is no equipment route and no effective secondary shot, an empty
gun can use a nearby wall until it refills. Six paired map cases show 180–315
more HP at the same 2.5-second refill. It can take longer to re-engage. After
12 seconds the paired average was 76 more current HP with the opponent at
134 less HP. These models establish mechanism and tradeoffs in controlled
encounters. The official scorer measures the combined policy's placement.

All 180 local tests passed. The official checker answered 300/300 on time,
with a 6.8 ms maximum. Crowded and growing-body maxima were 20.51 and
25.40 ms.

The integrated policy preserved the same 240 HP mean gain at the refill in
the six actual-map reload cases. At 12 seconds it had 90 HP more and the
opponent had 157 HP less on average than with the 4.04 policy. In one case
it traded less outgoing damage for more health. The physical moving-head
check still landed 45 damage through the open part of the target and withheld
the shot behind a full-height wall.

Commit `ff4e5bfe8acea9d4d53a88618f0a4b703f42d3c6` passed all 180 Linux tests
and the pinned image build. The restricted container answered 300/300 on
time, with p99 9.7 ms and maximum 10.2 ms. The tree was 2,466,118 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44951199088)

Receipt `BB-D807ACA6` scored this exact commit **3.98** after acceptance at
4:27 PM EST on November 21, 2026. The 4.04 entry remained selected. The
controlled gains did not produce a higher aggregate practice score.
