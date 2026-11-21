# Revision 7: return gun fire while recovery is interrupted

Baseline: revision 4, **3.21** placement points. This experiment adds one narrow
self-defense exception to the existing recovery firing policy. It does not adopt
the roof, shared-aim, or lightning-preference experiments.

## Finding and hypothesis

The baseline stops optional fire while recovering: a healthy enemy beyond 28 m
is not a combat target, even when it keeps hitting us. The published rules say
both dealing and taking damage interrupt health regeneration for five seconds.
Silence makes sense after escaping, but cannot produce healing under continuous
incoming hits. Brief gun retaliation may remove or weaken a pursuer while the
existing movement policy continues escaping.

On the same 300 kit observations, both policies entered recovery on 194 frames.
There were 45 recovery frames within one second of an incoming weapon hit. Gun
trigger frames during recovery rose from 0 to 3. These are recorded-policy output
counts, not rounds fired, damage, or placement predictions; recorded observations
do not react to the bot's actions.

## Isolated change

- Remember the time of incoming weapon damage separately from zone damage.
- For one second after such a hit, allow the gun to target visible enemy mechs
  that recovery would otherwise exclude. Aim, range, cover, ammo, and reload
  constraints still apply.
- Do not enable secondary weapons for these newly permitted targets: a new laser
  charge would halve escape speed, and lightning spends energy needed to escape.
- Stop the exception when incoming hits cease. Outgoing hit events and zone damage
  never extend it. Existing close defense, weak-target finishes, and final-duel
  rules retain their previous behavior.

The only runtime changes are in `sentinel/strategy.py` and `sentinel/combat.py`.
Goal scoring, movement, routing, weapons chosen, upgrades, and recovery thresholds
are unchanged. Holding a different aim and firing can still change what the bot
sees and what happens in a real match.

## Tests and limits

Nine new tests cover escaping while firing, quiet recovery, outgoing-hit and
zone-damage exclusion, the one-second expiration, aim/ammo/reload discipline,
secondary suppression, cover/range/passive targets, unchanged healthy combat,
and a limited gun-clock pressure scenario. That scenario sustains incoming hits
for eight seconds, produces at least 20 shots, and then stops optional firing
after the pressure ends. It does not model the opponent, damage taken, collision
physics, regeneration amounts, or placement.

All 48 behavioral tests pass locally. The official checker answered all 300
observations on time with no malformed, stale, or wrong-tick responses; maximum
response 8.1 ms. Synthetic crowded and growing-body timing checks remained below
50 ms, with maxima 19.64 and 18.94 ms on this Windows machine.

Return damage can delay healing after an escape: the one-second permission plus
projectile flight time is a real tradeoff. It also produces sound. The scored
practice run will determine whether the exception improves this fixed practice
comparison; no improvement is claimed before that result.

To reproduce the recording audit:

```sh
python3 tools/audit_recovery.py
python3 tools/audit_recovery.py --project-dir /path/to/archived/baseline
```
