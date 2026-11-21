# Revision 33 gets armed and stays oriented through the next fight

The selected 4.04 controller can lose a winnable fight by missing nearby gear.
It can also lose several rear hits while turning toward the next attacker.
This candidate pairs the short equipment route of revision 28 with the
confirmed incoming bearing of revision 30. It can use an instant defensive
arc while healing is already interrupted, provided enough energy remains
for movement.

The equipment route leaves ordinary gun aiming and firing in control and
ends at the real pickup. The bearing keeps a damage direction for 1.1
seconds when there is no combat aim. A new damage direction or a verified
target can take precedence. The arc exception applies only during ordinary
return fire and within the lightning weapon's real range.

The controlled continuous trial uses two legal pickup positions and two
seeds on the public map. The first fight begins with a full gun and each
opponent advances and shoots. Health, ammunition, energy, kill cubes, and
the first real upgrade carry into the following duel. The combined policy
and the equipment-only policy end the first fight in the same state. The
equipment-only policy loses to the second opponent in the current four
paired runs. The combined policy clears all four within 34.8 seconds of
the start, with 584.64 HP at the end of each, after the remaining hostile
rounds have resolved.

The second opponent is seen by 28.8 seconds, about half a second after
its first hit. Only the first two hits get the rear bonus. None of the
combined runs enters the recovery state against the second opponent, so
these clears do not measure the arc exception. The separate recovery
trial showed additional arc damage in four cases with 9–18 extra energy
spent. Later paths can vary with bounded search time. These are public-map
diagnostics, and the official run is the placement measurement.

All 150 local tests passed. The official checker answered 300/300 on time,
with a 6.8 ms maximum. The crowded and growing-body maxima were 12.15 and
13.19 ms.

Commit `48bc90e0eeb22fb2bd5b58bcabd680c58c187177` passed 150 tests and the
pinned Linux build. The restricted container answered 300/300 on time,
with p99 9.5 ms and maximum 10.2 ms. The tree was 2,419,762 bytes.
[Linux check results](https://github.com/Muallim718/oval-sentinel/actions/runs/44953279696)

Receipt `BB-9EC89CD5` scored this exact commit **4.02** after acceptance at
4:57 PM EST on November 21, 2026. The 4.04 entry remained selected.
The combined policy's gains in the two-wave model did not raise placement
on the private 48-match practice run.
