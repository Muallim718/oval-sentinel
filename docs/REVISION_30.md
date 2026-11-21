# Revision 30 keeps an unseen incoming shooter in view long enough to turn

A damage observation gives a world-frame direction toward the source.
The original fallback aims that way for one observation and may go back
to its normal scan on the next. The torso can take almost 0.8 seconds to
turn around at the stock rate.

The new fallback remembers a confirmed mech damage bearing for 1.1 seconds.
It applies while there is no real combat aim. A new damage report can
replace it, and a kill receipt clears the defeated attacker's bearing.
The direction controls the torso. Movement and trigger logic still use
actual observations.

In one paired 20 Hz test with two consecutive fights on the public map,
the first shot from an unseen second opponent landed at 28.4 s in both
runs. The 4.04 controller first saw that opponent at 30.2 s. The new
fallback first saw it at 28.9 s. Four hits that previously got the rear
bonus landed against frontal armor. The bot had 92.7 more HP at 30 s.
It still lost the later duel. This comparison establishes the turn and
rear damage effect in that encounter.

All 128 local tests passed. The official checker answered 300/300 on time,
with a 6.2 ms maximum. The crowded and growing-body maxima were 11.93
and 17.73 ms.
