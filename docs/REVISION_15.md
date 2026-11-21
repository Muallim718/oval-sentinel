# Revision 15: charge and reload behind a corner

In the 3.73 controller, a laser normally charges with a clear shot while the
mech moves at half speed. The corner controller looks for a covered point
and a nearby firing point linked by a ground corridor that fits the entire
mech. It holds the charge behind cover, moves just far enough to release an
aligned beam, and returns behind the wall during the cooldown. It needs a
recently tracked opponent, enough time before a hunter can round the corner,
and clear geometry on both positions and the return route.

The bot tracks when it reaches full charge even if the reported charge stops
increasing at 0.75 s. It ends a peek before automatic release would spoil the
shot. It yields to approaching crossfire, reduced energy, a changed zone, or
body growth. If the target dies or goes stale during a peek, the controller
owns the return until the mech reaches cover. The ordinary movement and
kill-reward policy continue outside the corner cycle.

In an independent eight-second gun-pursuit model, the baseline gave 630 damage
and took 315. The corner policy gave 450 and took 135, keeping the same net
damage margin and 180 more current HP. It spent 44 energy, used 1.45 s of
exposure instead of 2.10 s, and returned to cover at 2.75 s. The same case
worked with either capped or elapsed charge reports. The model demonstrates
one repeatable corner trade. It cannot establish typical use or placement.

All 121 local tests passed, including 16 corner policy and seven physics
feedback tests. The official checker answered 300/300 on time with an 8.8 ms
maximum. Local host crowded and growing-body maxima were 17.70 and 13.05 ms.
Forty separate public-map corner probes found four feasible pairs, with module
timing median 0.804 ms and maximum 3.248 ms on this machine.

Commit `d897246cdea06bbdf4658e4d78fc729c5ca26cb2` passed 121 Linux tests and
the pinned image build. The restricted container answered 300/300 on time,
with p99 5.8 ms and maximum 15.3 ms. The submitted tree was 2,339,246 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44945221109)

The practice service accepted the exact commit at 3:15 PM EST on November 21,
2026, under receipt `BB-149421CA`. It scored **3.58**, 0.15 below the 3.73
baseline. Aggregate scoring cannot explain how often the corner cycle found
an opportunity or which interactions changed placement. The baseline remains
selected and the implementation stays on
[`experiment/laser-corner-cycle`](https://github.com/Muallim718/oval-sentinel/tree/experiment/laser-corner-cycle).
