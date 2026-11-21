# Short equipment acquisition during a reload

The isolated equipment experiment starts from the selected 4.04 runtime commit
`47a4d7d56a20a274dd8c38f946c8456fc9fa8176`. It adds a movement commitment to
an observed weapon within a three-second ground route. The brawler still owns
its duel, target, aim, triggers and normal health decisions. Salvage and the
existing opening controller take priority. Receipt immediately ends the route;
the server's initial equipment cooldown remains authoritative.

An exposed new route must fit the bot's own gun's observable
remaining reload. A fully protected short route can also collect during healing.
Risk includes arrival plus the new weapon's equip delay. No enemy reload state
is inferred by the policy, and no pickup is invented from a sound or kill.

## Controlled comparison

`tests/test_reload_arm_feedback.py` runs the real baseline and candidate Bots at
10Hz inside the existing20Hz ground/gun diagnostic. The scene begins after an
even exchange: both mechs have1000HP and both guns are actually reloading for
2.4s. The hunter is80m east; one real weapon is10m west of the player. Both have
100 energy. The usual diagnostic hunter pursues, boosts beyond65m while energy
permits, stops closing within35m, aims with constant-velocity lead plus its
existing fixed perturbation, and fires whenever it has a valid gun lane. It
does not stop behind a wall to provide a free recovery interval.

The real baseline may collect the weapon through its normal passive take rule.
It does not do so in this fixed scene. The candidate makes its short detour
while preserving aim and the brawler's target. Weapon acquisition requires the
actual take action within4m horizontally/4m vertically. Laser equip is1.65s;
lightning equip is1s. The model prevents charging or firing during equip.
Gun bullets use continuous segment/cylinder collisions. Laser beams use actual
torso direction and map collisions, published charge/minimum/hold/cooldown, and
the half-speed movement penalty. Lightning spends energy and only damages a
target inside its actual cone and range. Explicit tests reject out-of-range
and sideways lightning hits.

| Diagnostic | Baseline4.04 | Laser pickup | Lightning pickup |
|---|---:|---:|---:|
| Pickup time | none |0.60s|0.60s|
| Equip ready | none |2.25s|1.60s|
| First secondary emission | none |3.00s|2.10s|
| Actual secondary hits / damage |0 /0|2 /630|10 /600|
| Gun shots |23|12|9|
| First kill time |10.35s|5.40s|4.40s|
| Own HP at first kill |55|460|595|
| Damage received by first kill |945|540|405|
| Healing |0|0|0|
| Remaining energy |47.7|100|70|

The model stops at the first kill or own death; HP here is **at the first kill**,
not a claim about later hunters or every projectile still in flight. This is a
favorable, explicitly shared-reload opportunity. The policy does not know that
the hunter is reloading and budgets damage conservatively anyway. The frequency
of useful nearby weapons and such windows in private scored matches is unknown.
These results show actual acquisition and useful secondary fire in this scene,
not a placement prediction or a promise that every pickup pays for its detour.

Run each project in a fresh process to compare exact runtime sources:

```powershell
git worktree add --detach ../oval-sentinel-4.04 score-4.04
py -3.13 tests/test_reload_arm_feedback.py --simulate ../oval-sentinel-4.04 laser
py -3.13 tests/test_reload_arm_feedback.py --simulate . laser
py -3.13 tests/test_reload_arm_feedback.py --simulate ../oval-sentinel-4.04 lightning
py -3.13 tests/test_reload_arm_feedback.py --simulate . lightning
```

The untouched baseline archive is made from the exact commit above. The model
still approximates authoritative ordering, visibility and house behavior. It
does not simulate mortar combat, air movement, upgrades or a complete match.
