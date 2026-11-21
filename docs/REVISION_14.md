# Revision 14: finish weakened opponents when the damage budget allows

The 3.63 controller sometimes abandons an open fight after its one-second
return-fire window even when the opponent is a few confirmed hits from defeat.
Healing still needs five quiet seconds. Giving up the attack can leave both
mechs alive and give the opponent time to recover.

The new policy looks for a short, breakable opportunity backed by observed
hits, recent damage received, and the actual ammo, reload, cooldown, and
charge. A gun finish must fit in the current magazine and a two-second
window. A laser finish uses charge already on the weapon. Prospective damage
from another charging sequence does not qualify. The estimate accounts for
projectiles already fired during a committed gun burst until they hit or the
estimated flight window expires.

The bot preserves the selected weapon and target while the estimated burst is
viable. It keeps the usual steering, vetoes another credible attacker, and
returns to its normal policy when a shot is obstructed, the battle reserve
falls too low, or the zone makes the finish unsafe. It keeps a confirmed
shelter rather than leaving it to force a finish.

An independent 20 Hz model starts with 725 own HP, a 225 HP opponent at
75 m, eight rounds, and a plausible prior damage record. The old return-fire
window has expired. The candidate kills at 1.15 s with six shots and five
confirmed hits, retaining 725 HP. The baseline fires zero shots and the enemy
still has 225 HP at 1.95 s. Exposing a second hunter or moving the
forecast circle after the first shot immediately cancels the commitment.
This controlled case exercises timing and feedback. Live placement also
depends on the house opponents, terrain, and the rest of the match.

Local verification passed 98 tests, including 13 policy cases, three full Bot
controls, and two physical feedback tests. All 300 official replies were on
time with no protocol errors and a 9.1 ms maximum. Crowded and growing-body
host maxima were 17.44 and 12.66 ms.

Commit `0cb62afeef79b6fc0d6e4f908a2ecdcc94424aad` passed all 98 Linux tests,
the pinned image build, and 300/300 on-time replies in the restricted sandbox.
The maximum was 14.1 ms and p99 was 5.5 ms. The submitted tree was 2,296,693
bytes. [Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44944382877)

The practice service accepted the exact commit at 3:07 PM EST on November 21,
2026, under receipt `BB-34293991`. It scored **3.58**, below the independent
3.63 baseline and the selected 3.73 salvage version. The promising controlled
finish did not improve aggregate placement. The code stays public on
[`experiment/lethal-commitment`](https://github.com/Muallim718/oval-sentinel/tree/experiment/lethal-commitment).
