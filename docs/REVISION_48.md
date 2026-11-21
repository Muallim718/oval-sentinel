# Revision 48: improve the first fight through equipment and upgrades

The ordinary gun has two long reload gaps before it can defeat a fresh
opponent. One reachable secondary, or a better first magazine, can decide
the opening fight. This candidate combines revision 47's short equipment
routes with the upgrade selector on top of the 4.31 recovery controller.

The mech keeps aiming and firing while it reaches a checked nearby
secondary. If it is still gun-only and an upgrade is offered, it compares
the live gun clock with the alternatives. A magazine upgrade changes
capacity when the gun next reloads. It does not supply free rounds.
Protected repair still has priority over equipment movement, and a
repair-speed upgrade must have a demonstrated short-window benefit.

The actual-map diagnostics exercise these separately. The short route
reaches the secondary at 0.8 seconds in four legal starts and defeats the
first hunter in each. With an identical one-cube reward and first upgrade
offer, the drum candidate defeats the first gunner 2.7 seconds earlier
and with 162 more HP in both tested seeds. Those tests use independent
physical scenarios and provide no practice placement estimate.

Exact commit `4c1771bffe8fd491d70ca2be65aa3fc0884db712` passed
[Linux and the restricted container](https://github.com/Muallim718/oval-sentinel/actions/runs/44960178611).
All 172 tests passed. The container answered 300 of 300 observations
on time, with p99 11.7 ms and a 13.2 ms maximum.

Practice receipt `BB-17BBAF1E` scored **4.50** on November 21, 2026 at
6:10 PM EST. This raised the selected score by 0.19 and corresponds to
11.50 mean placement across 48 matches. The site selected it automatically.
