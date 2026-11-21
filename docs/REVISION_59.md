# Revision 59: orient sooner using sound and confirmed hits

This variant keeps the attention changes from revision 57 on the scored
4.50 controller. Gun and laser solutions use the original 4.50 solver.

Anonymous recent sound can direct a quiet scan. After an attributed hit,
the last real bearing stays available while the torso turns and there is
no useful current shot. Ammo, route, and repair decisions continue to come
from the selected controller.

In the actual-map three-wave diagnostic, either attention cue is enough to
produce earlier second contact in four cases. Disabling both while keeping
the exposed-body solver delays contact to roughly 29.4 to 29.7 seconds and
leaves no third-wave survivors. Keeping both cues and removing the
exposed-body solver still clears all four. These comparisons test the local
mechanism. Practice runs measure placement.
