# Revision 28 arms the mech before the first magazine is empty

Waiting for a gun reload can forfeit a useful nearby secondary. The mech
and the hunter may be closer and hundreds of HP lower by the time the first
magazine empties. This candidate adds a short equipment route while the
ordinary controller continues aiming and firing the gun.

The route must reach a visible laser or lightning pickup in at most 1.25
seconds. The mech must have at least 78% HP and face one gun-only opponent
at least 52 m away. The route cannot draw appreciably closer to that threat.
It must fit live body clearance and the zone. Estimated damage includes
the actual equip delay. Damage, lost access, or the fixed deadline returns
ordinary movement. The existing reload and covered routes remain available.

The paired actual-map diagnostic preserves all health, guns, cubes, and energy
across two reactive opponents. At the cover-side pickup, the 4.04 controller
missed the weapon and lost the first fight at 11.8 s in both tested seeds.
The candidate took the same lightning at 0.8 s, equipped at 1.8 s, and won
both first fights at 5.4 s with 815–860 HP. At the other legal pickup, both
baselines acquired lightning later. The candidate still won its first fight
earlier and with more HP. Survival against the three-cube second opponent
remained mixed. This tests acquisition and the first fight in four controlled
starts. It does not establish a placement gain across private seeds.

All 146 local tests passed. The official checker answered 300/300 on time,
with a 6.7 ms maximum. The crowded and growing-body maxima were 11.95 and
14.04 ms.
