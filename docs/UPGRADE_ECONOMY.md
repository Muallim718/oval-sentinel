# First upgrade choices

The original prototype started from `score-4.04`. This version uses
`score-4.31`, including its check for an active repair window. The selector
uses the live gun and focused opponent to evaluate the upgrade actually
offered. The ordinary priorities still apply when they have a more immediate
defensive or movement benefit.

The old fixed order scores servos100, plating96, armor94, gun damage93, gun
rate92, nanites90 and drum magazine85. It therefore rejects the first magazine
upgrade in many gun-only offers despite its large reduction in reload overhead.

## Exact effects and quantitative references

Effects are read from `hello.config.upgrades`, not offer descriptions. Current
weapon statistics already include cubes and previous upgrades. The comparison
uses those live numbers. Current ammo and timers are conservatively retained;
the protocol does not promise an instant refill when capacity increases.

The simple cyclic reference is `damage * magazine / (magazine * cooldown +
reload)`. It is useful for marginal comparisons, not authoritative tick order.

| Choice on the base gun | Magazine capacity | Ideal full-mag damage | Cyclic DPS | Change |
|---|---:|---:|---:|---:|
| Existing |12|540|102.273|—|
| First drum |20|900|133.929|+30.95%|
| Damage |12|621|117.614|+15.00%|
| Fire rate |12|540|110.078|+7.63%|
| Second drum, after first |28|1260|152.616|+13.95% over first|

An independent20Hz weapon timer /10Hz trigger-and-reload clock includes reload
overlap, decision delay and tick quantization. Every emitted shot is counted as
ideal reference damage; accuracy and projectile flight are **not** simulated.
It starts with the existing 12 rounds even when comparing the drum upgrade.

| Upgrade |120s ideal emitted damage / second | Clock to emit1400 damage |
|---|---:|---:|
| None |108.0|11.70s|
| First drum |139.5|9.15s|
| Damage |124.2|10.75s|
| Fire rate |117.0|10.80s|

This clock gives the drum a29.17% throughput increase. The discrepancy from the
analytic30.95% is why these are separate labeled comparisons. Neither is a
prediction of scored damage, kills or placement.

Nanites have a similarly concrete timing effect. Starting a **new** quiet
interval with700/1400HP gives:

| Repair configuration | Delay | Rate | Healing by5s | Time to the controller's90% HP threshold |
|---|---:|---:|---:|---:|
| Base |5s|45/s|0|17.44s|
| One nanites |3.5s|72/s|108|11.28s|
| Two nanites |2s|115.2/s|345.6|6.86s|

Healing is capped by missing HP. Dealing or taking damage resets the quiet
clock, and storm damage prevents repair. These figures do not assume a pursuer
will allow a five-second shelter window. Plating's description guarantees15%
more maximum HP; this prototype does not infer an immediate heal from it.

## Limited choice policy

- Preserve the old priorities for urgent storm movement, low energy, critical
  health, an actively charging opponent, secondary builds and late fights.
- In actual sheltered recovery, prefer offered nanites only when the live
  five-second repair improvement is at least one base gun hit. Do not assume
  safety while taking damage or when the existing repair already fills HP.
- In an early gun-only build, promote the first drum when its live throughput
  improvement beats the offered gun alternatives. An observed nearby threat
  without an accepted duel prevents treating the situation as quiet economy.
- For a caller-provided isolated duel, use current ammo/reload and actual enemy
  HP to compare offered gun firing clocks. A drum can lose to damage on a close
  finish, or a second drum can win when it avoids another reload. No free ammo
  is credited when evaluating either case.
- Otherwise retain the old order. Unknown IDs retain a valid stable fallback;
  an expired offer returns documented default index0. Names and descriptions
  never control the policy.

## Side effects and limits

Larger magazines encourage longer firing bursts and provide fewer reload
windows for movement or opportunistic arming. Shorter reloads also provide less
time behind cover. Nanites do nothing while damage continues; a normal reload
alone is shorter than the first nanites delay. Armor still reduces incoming
weapon damage immediately, and servos still provide8% more movement speed.
Unmodeled hit rate, exposure, pursuit, secondary use and weapon availability can
outweigh an ideal gun throughput improvement.

All14 focused tests pass. They cover live effects, current-ammo conservation,
first and second stack choices, real health caps, recovery conditions, urgent
mobility/defense, unknown offers and malicious descriptive text. A10000-call
probe measured approximately0.006ms median and0.09ms maximum selection time on
this host. No practice result is claimed for this prototype.

```powershell
py -3.13 -m unittest discover -s tests -p test_upgrade_economy.py -v
```
