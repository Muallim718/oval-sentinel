# Revision 10: take a roof before the fight arrives

Baseline: revision 8, **3.63** placement points. The 3.58 readiness experiment is
not included. This attempt adds proactive roof access and persistent elevated
holding while retaining the proven ground controller as fallback.

The older revision 3 combined late roof recovery with matchup estimates and
body routing and scored 2.58. This is a different strategy: take off while healthy
and unpressured, cross only to an entry before walking deeper, and keep control
of the roof even after health is restored. Its success is not assumed from the
previous experiment or from flight tests.

## Controller

`sentinel/altitude.py` derives candidate launch columns, entries, and deep hold
positions from public building prisms. It requires supported body-sized roof
disks, clear vertical columns, a checked crossing, and a supported roof path.
Courtyard holes, overhangs, live body growth, and energy requirements can reject
a site. It generates 200 sites on the supplied map for the starting body.

Preemptive launch requires at least 90% HP, 85 energy, five seconds without
damage, no charged laser, no known hunter within 180 m, and no known firing lane
at the current or planned launch position within the attacker's range. Unknown
enemies remain a risk; these checks are not private information or immunity.

The phases are approach, ascend, cross, land, settle, hold, and exit. The final
approach meters use explicit braking and an actual-position clearance recheck.
After crossing to an inset entry, the mech lands and walks deeper rather than
spending jet energy across the entire roof. A healthy hold persists rather than
returning control to ground navigation and walking off the roof.

The predicted circle triggers an early physical exit toward a clear outside
column. A blocked exit retries another edge; making progress across a wide roof
extends its watchdog. Grounded on a roof does not count as terrain landing.
Altitude control is retained through the descent and released on actual ground.

Height alone does not make the position safe. A new weapon hit while holding, an
exposed charging laser in range, an elevated nearby opponent, invalid body
clearance, or an unsuitable circle can trigger exit. Healthy unpressured holds
can use ordinary validated combat. Flight and hurt holds suppress optional
shots. Existing reload, upgrade, and nearby pickup handling is shared with the
ground path, preserving the gun and avoiding premature partial reloads.

## Work budget and validation

Roof generation occurs at startup. Candidate search cheaply ranks nearby sites,
checks at most 12 per search with a 6 ms budget, and caches static clearance by
live body dimensions. Quiet-map timing is tested separately: crowded inputs
would immediately veto a proactive launch and miss this branch.

The suite contains the previous 80 tests plus eight core roof tests, ten
independent flight/physics tests, and eighteen full-bot altitude integration
tests. The [flight model](ALTITUDE_MODEL.md) completes 12, 25, and 40 m synthetic
flights and four public-map roofs, with physical jumps, energy use, ceilings,
wall collisions, edge support, landing, holding, and zone exit. The highest
synthetic case retains 29.5 energy from an initial 100.

The controls were corrected using independent feedback when ground steering
stopped short of the launch and when rooftop PD motion prevented settling.
Integration checks also guard against handing a stalled roof back to ground
navigation, remaining under weapon pressure, ignoring passive pickups, and
reintroducing partial-magazine combat reloads.

These checks establish physical plausibility and protocol compliance, not an
advantage against the house squad. Combat during ascent and exact server eave
handling remain unmodeled. The scored comparison decides whether this strategy
is retained. Linux validation and the scored receipt follow after completion.

Final local verification: **116 tests passed**, official checker **300/300**
on-time replies, zero protocol errors, startup 413 ms, p99 response 3.6 ms and
maximum 9.1 ms. Crowded and growing-body timing maxima were 21.58 and 22.76 ms.
The separate 40-position quiet-map check started 12 roof plans, with maximum
decision 2.37 ms and maximum fresh-bot startup 419.7 ms; none exceeded 50 ms.

## Linux validation and scored entry

Commit `7edf73c69c0661c98cc1f2fd53096af62d130bf9` passed the
[Linux workflow](https://github.com/Muallim718/oval-sentinel/actions/runs/44930483153):
all 116 tests, pinned image build, and 300/300 on-time restricted-container
responses, p99 5.7 ms and maximum 14.0 ms. Linux host crowded/growing-body timing
maxima were 25.87/16.06 ms. Forty fresh quiet-map starts produced 12 roof plans,
with maximum decision 3.54 ms and startup 558.3 ms; no decisions exceeded 50 ms.
The committed source was 2,303,209 bytes, below 20 MB.

Receipt `BB-7E1DFF95` was submitted at 12:33 PM EST on 2026-11-21 and scored
**3.40**, 0.23 below revision 8. The 3.63 entry remains selected.

Code review after submission found an important limitation: the zone check
requires the abandoned ground launch point to remain safe even after landing.
It can therefore force an exit from a roof whose holding position is safe.
The immutable scored candidate is preserved on `experiment/proactive-roofs`;
a corrected comparison will distinguish this control flaw from the wider roof
strategy. The aggregate result alone cannot establish the cause of the decline.
