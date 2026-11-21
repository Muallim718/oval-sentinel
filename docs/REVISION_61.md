# Revision 61: add a short finish after earlier contact

This variant adds revision 56's target selection to the full perception
controller from revision 57. It starts the short target window only when the
gun has a clear center lane. The ordinary scheduler can still use an
exposed part of a body when terrain blocks its center.

Both changes run through the existing equipment and recovery controller.
The first finds observed contacts sooner. The second keeps a weak,
already-aligned attacker in the gun's aim during a short burst.
