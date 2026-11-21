# Collect during observed regeneration

This experiment starts from the high-value verified-route prototype `cf6fe72`,
which is based on the official4.50 bot. It changes optional detour authorization,
not the established direct eight-second kill-reward policy.

A blocked or extended reward route now needs two adjacent observed HP increases
at a plausible regeneration rate. Maximum HP, cube count, and upgrades must stay
unchanged. Hits, damage, pickups, kills, gaps and unexplained HP jumps reset this
evidence. Repeating one observation cannot manufacture healing.

A new recovery approach:

- Needs at least four currently visible compact cubes associated with a real
  recently confirmed kill. Remembered or missing cubes cannot extend freshness.
- May finish within twelve seconds of that kill. Ordinary direct reward
  commitments keep the original eight-second deadline.
- Walks for at most four seconds; it does not sprint or start a blind jet.
- Retains exact pickup anchors, whole-route grown-body and return-path checks,
  predicted zone limits, actual projectile checks, arrival race and HP reserve.
- Stops for crossing rounds or credible current/predicted firing lanes. Passive,
  distant or screened actors still enter damage and race estimates; merely
  remembering one elsewhere does not globally veto the feature.
- Keeps optional firing quiet, including when health crosses normal recovery
  hysteresis. Actual pressure returns ordinary survival/attack control.

A cube bundle already accepted by this recovery mode stays subject to those
conditions while approaching it. Moving around its corner cannot silently
convert it into a faster unrestricted direct dash. The policy adds no HP, energy
or ammunition. Its reserve budget can value the fresh observed bundle's healing,
while damage that could kill before pickup remains a veto. Future regeneration
is not credited as already available HP.

The routed threat estimate also counts enemy magazines after a reload. A seven
second exposed route can face nineteen base gun rounds at100m, rather than the
old twelve-round cap. The ordinary direct estimator is unchanged.

## Local evidence and limits

The held-out public-map corner is player `(148,46)` to a five-cube bundle at
`(154,79)` around block31. Both full projected-growth endpoints and a complete
walking route fit; the straight body corridor is blocked while the native eye
ray sees the cubes. The pair was the first static grid match to declared
geometry criteria, before running either policy.

In a declared post-kill snapshot where the bundle first becomes visible6.2s
after the confirmed kill, the official4.50 and immediate-route prototype cannot
complete their eight-second window. With model seeds97/113, the new controller
observes actual ongoing regeneration, physically picks all five cubes2.85s into
the run, and ends at1130HP/seven cubes versus850HP/two cubes. Both regenerate450HP,
fire no shots and take no damage. The280HP difference is real cube growth.

With an immediately reactive gunner55m east, the new recovery approach never
starts. The qualified seed97 matches official4.50 exactly:96.92HP after10s,
712.08 damage taken and two cubes. The immediate-route prototype instead grabs
the reward under pressure and finishes near730HP: this is a real opportunity
cost of the stricter gate. Its practice score regressed from4.50 to4.35, which
does not establish that every under-pressure reward is bad.

The first seed113 negative run encountered unsupported grown-enemy collision at
7.8s; it remains excluded. Later valid reruns vary with elapsed-time-bounded
navigation and cannot establish superiority or nonregression for that case.
These are declared post-kill states, not full match replays. The generic model's
unrelated constructor hunter sighting was cleared consistently before each new
snapshot. Shared automatic-empty reload applies to both physical actors.
Original ground physics and earlier reports remain unchanged. No house-bot AI,
private seeds or placement prediction is claimed.

The exact local verifier passed198 tests, all300 official observations inside
the50ms deadline, and crowded benchmarks without late calls. The recorded
checker maximum was7.6ms; the busiest synthetic benchmark maximum was21.78ms.
Linux/container verification remains a separate required check.

```powershell
py -3.13 -m unittest discover -s tests -p test_regeneration_collection.py -v
py -3.13 tools/verify.py
```
