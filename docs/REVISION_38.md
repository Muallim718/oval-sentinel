# Revision 38: keep fighting while finding cover

The 4.19 controller treats recovery as both a route and a weapon restriction.
An exposed mech can lose the ability to use a ready secondary or return gun
fire while a previously identified pursuer is still closing. This revision
lets steering choose the escape route and keeps the weapons available against
the same observed attackers used by revision 35.

A current shelter or a confirmed rise in HP after a damage-free interval
reserves silence for repairs. The check rejects health added by cubes or
upgrades, and it looks for incoming rounds and exposed laser charge. A repair
already in progress takes priority over starting a new duel. While retreating,
the released weapon restriction applies to observed mechs only.

The public-map wave diagnostic checks physical gun and lightning damage,
weapon clocks, movement, and repairs. In the two starts without a weapon
pickup, both versions still lose with the first opponent at 5 HP. With the
same lightning available, the reference died twice with the second hunter
at 787.30 and 71.12 HP. The candidate cleared both waves at 125.75 HP in the
second case and left the second hunter at 397.71 HP in the first. There was no free
health, ammo, or movement reset. Small timing changes in the local navigation
search can change a close outcome. Official practice measures placement.

All 137 local tests passed. The official protocol checker received 300 of 300
on-time answers with a 7.9 ms maximum. The crowded and growing-body checks
had maximum decision times of 20.49 and 14.95 ms.

Commit `227cea87a7f24da9824d644b15f8524710f5c211` passed
[Linux and the restricted container](https://github.com/Muallim718/oval-sentinel/actions/runs/44957329210).
All 137 tests passed and the container answered 300/300 on time, with p99
9.1 ms and an 11.4 ms maximum.

Practice receipt `BB-D2773F9B` scored **4.31** on November 21, 2026 at 5:34 PM
EST. That is 0.12 above 4.19 and corresponds to approximately 11.69 mean
placement over 48 matches. The practice site selected it automatically.
