# Revision 11: use the roof through the closing zone

Revision 10's proactive rooftop strategy scored 3.40, below revision 8's 3.63.
Review found a concrete problem independent of that score: the zone check
continued requiring the abandoned ground launch to remain in the predicted
circle after the mech had landed. A safe rooftop could be abandoned merely
because its access point was outside the future circle.

This comparison corrects the rooftop controller on top of revision 10. It does
not include revision 9's readiness/resource experiment. The best ground-only
controller remains preserved by `score-3.63` and selected during evaluation.

## Intended behavior

Before takeoff, the launch, entry, and original hold must all be safe. After
takeoff, the old launch is no longer a zone requirement. A landed mech validates
the roof it currently occupies and a live holding destination. It can keep a
safe hold or walk to another supported, body-clear point on the same roof.

The live destination is separate from immutable cached launch sites. Candidate
anchors are bounded, and the route must stay supported without crossing a
courtyard hole. A destination inside the future circle may require walking
from a position outside that future circle; such a path must remain inside the
current observed zone while progressing inward. Small circles use a scaled
margin instead of the original fixed 12 m margin.

If no usable same-roof position exists, the controller retains movement
ownership through a physical exit and descent. Weapon pressure, lost support,
and unsuitable body clearance still trigger the existing safety behavior.

## Validation and outcome

All **141 tests passed locally**: the previous 116, one additional body-fit
case, eight core zone cases, four independent physical feedback cases, and
twelve full-bot integration cases. The older growth case now verifies that a
wide, clear roof remains usable after the original entry becomes unsuitable;
the additional case still requires an exit when the body actually cannot fit.

Physical feedback holds for eight seconds when the old launch is outside a
future 25 m circle, finishes an already airborne flight under that forecast,
walks to a supported position in a shifted 5 m circle without extra jump/jet
use, and completes a real descent when the predicted circle moves off the roof.
All seven earlier flight cases still pass. Integration checks keep actual hit
and charging-laser exits active on subsequent ticks of a rooftop retarget.

The local official checker returned **300/300 on-time replies**, zero protocol
errors, p99 3.6 ms and maximum 9.1 ms. Crowded/growing-body host maxima were
22.83/12.87 ms. Forty quiet starts produced 12 roof plans, maximum decision
2.91 ms. A separate 160-call active-retarget benchmark across 40 public roofs
reported p99 5.98 ms, maximum 6.65 ms, and no calls above 50 ms. That last
benchmark measures the altitude controller, excluding the rest of the bot and
protocol I/O; the official checker includes those costs on its recorded stream.

Commit `c70818c75148d369b713e03010cbce44bf0ac4e8` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44932195013):
all 141 tests, the pinned image build, and 300/300 on-time restricted-container
replies. Container p99 was 7.2 ms, maximum 16.6 ms. Linux host crowded/growing
maxima were 31.21/31.13 ms. Quiet starts had maximum decision 4.49 ms; active
retargets had p99 12.35 ms, maximum 14.02 ms. No timing samples exceeded 50 ms.
The submitted tree contains 61 files and 2,344,126 bytes, below 20 MB.

Receipt `BB-002475DD` was submitted at 12:52 PM EST on 2026-11-21 and scored
**3.31**, 0.09 below the original roof experiment and 0.32 below revision 8.
The zone-control defect is fixed in controlled tests, but the strategy did not
improve the aggregate practice score. No match-level breakdown was available,
so the cause of the decline is not established.

The 3.63 entry remains selected. Revision 8's runtime, tests, and verification
command were restored exactly on `main`. The full 141-test roof candidate and
its timing tools remain public on
[`experiment/roof-zone`](https://github.com/Muallim718/oval-sentinel/tree/experiment/roof-zone).
Run the roof-specific checks from that branch, not the ground-only default.
Controlled feedback cannot predict placement or reproduce authoritative server
physics, combat, or storm damage during a full moving-zone match.
