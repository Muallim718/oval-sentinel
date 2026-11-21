# Revision 20 sees isolated early duels through

The largest measured gain in the early revisions followed a repair to
sustained fire. The 3.75 controller still changes to avoidance an instant
before or during a close contest when its health falls below 70%, even
against a weaker opponent. This candidate keeps one credible target through
that transition and closes to a range where the gun needs less lead.

With more than eight mechs remaining, it can commit to the nearest observable
mech with a clear lane. It preserves the target across small distance changes.
The normal gun range becomes 42 m in those fights, with different spacing for
lightning and a laser facing a mortar. A loaded gun and at least 64 energy are
required to sprint toward a distant opponent. As health falls it requires
the target to be weaker. Crossfire, another source of damage, a storm threat,
or ongoing sheltered healing restores the ordinary controller.

The 300-frame kit recording shows a change from 30 to 57 fight decisions and
from 14 to 53 boost requests. It shows 27 gun-trigger requests for both policies.
The recording is fixed and does not show the consequences of the new movement.
All 125 local tests and the official checker passed. The official checker
answered 300/300 on time. The maximum was 6.6 ms, and the local crowded and
growing-body maxima were 21.86 and 12.87 ms.

The paired 20 Hz trial gives the opponent its own copy of the 3.75 controller
and ordinary vision, movement, cover, and gun feedback. It uses two held-out
seeds and two plausible orders for aim slew and weapon fire. The baseline
finished with no wins, 16 timeouts, and four crossfire losses. The candidate
finished with six wins, 10 timeouts, and the same four losses. It killed all
four weaker opponents and two of eight equally healthy opponents. It used more
HP in the single-opponent cases. The equal-health wins occurred under one
firing order. The four crossfire traces were identical. The model measures
the choice to continue a duel on this terrain and these opponents.

Commit `47a4d7d56a20a274dd8c38f946c8456fc9fa8176` passed all 125 Linux tests
and the pinned Linux image build. The restricted container answered 300/300
on time, with p99 12.9 ms and maximum 14.9 ms. Crowded and growing-body Linux
host maxima were 35.64 and 37.64 ms. The tree was 2,356,342 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44948886648)

Receipt `BB-5EE1F65A` scored this exact commit **4.04** at 4:00 PM EST
on November 21, 2026. The site selected it as the team's best. The gain
over 3.75 was 0.29 placement points across the 48-match practice run.
The aggregate score does not identify which match situations improved.
