"""Sound evidence and a small physical FOV/acquisition timing comparison.

The latter models yaw slew, real vision entry, moving hunter shot origins and
continuous incoming bullet/cylinder crossings. It does not fabricate damage
from outgoing shots or claim to reproduce the house AI.
"""
import math
import random
import unittest

from test_bot import fixture
from sentinel.geometry import angle_error
from sentinel.sound import SoundScout


class SoundTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.scout = SoundScout(hello["config"])
        self.obs.update(t=10, tick=200, sounds=[])
        self.obs["self"]["aim"] = [math.pi, 0]

    def cue(self, bearing=1, kind="gun", band="far", age=0):
        self.obs["sounds"] = [{"kind": kind, "bearing": bearing, "dist": band, "age": age}]
        self.scout.update(self.obs)
        return self.scout.heading(self.obs["t"])

    def test_single_far_shot_orients_immediately_without_inventing_a_position(self):
        heading = self.cue()
        self.assertIsInstance(heading, float)
        self.assertAlmostEqual(heading, 1)
        self.assertEqual(self.scout.state, "watch")
        self.assertGreaterEqual(self.scout.initial_watch, (math.pi-math.pi/3)/4+.1)

    def test_nonoffensive_stale_and_invalid_cues_do_not_control_heading(self):
        for kind, age, bearing in (("step", 0, 1), ("gun", .5, 1),
                                   ("gun", 0, float("nan")), ("drop", 0, 1)):
            with self.subTest(kind=kind, age=age):
                self.setUp()
                self.assertIsNone(self.cue(kind=kind, age=age, bearing=bearing))

    def test_bearings_average_across_pi_and_repeated_cues_extend_watch(self):
        self.obs["self"]["aim"] = [0, 0]
        self.cue(math.pi-.08)
        first_until = self.scout.active["until"]
        self.obs["t"] += .25
        self.obs["tick"] += 5
        heading = self.cue(-math.pi+.08)
        self.assertLess(abs(angle_error(heading, math.pi)), .01)
        self.assertGreater(self.scout.active["until"], first_until)
        self.assertEqual(len(self.scout.clusters), 1)

    def test_repeated_far_shots_cannot_monopolize_scan_forever(self):
        start = self.obs["t"]
        headings = []
        for i in range(26):
            self.obs.update(t=start+i*.1, tick=200+i*2)
            headings.append(self.cue())
        self.assertIsNotNone(headings[0])
        self.assertIsNone(headings[17])
        self.assertTrue(all(h is None for h in headings[17:25]))

    def test_closer_or_charging_cue_preempts_without_equal_priority_pingpong(self):
        self.cue(0)
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.assertAlmostEqual(self.cue(2), 0)  # Equally urgent unknown gun.
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.assertAlmostEqual(self.cue(2, band="near"), 2)
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.assertAlmostEqual(self.cue(-1, kind="laser_charge", band="mid"), -1)

    def test_anonymous_noise_state_is_bounded_and_expires(self):
        self.obs["sounds"] = [{"kind": "gun", "bearing": i*math.tau/12,
                               "dist": "far", "age": 0} for i in range(12)]
        self.scout.update(self.obs)
        self.assertLessEqual(len(self.scout.clusters), 8)
        self.scout.heading(self.obs["t"])
        self.assertIsNone(self.scout.heading(self.obs["t"]+2))
        self.obs.update(t=13, tick=260, sounds=[])
        self.scout.update(self.obs)
        self.assertFalse(self.scout.clusters)

    def test_repeated_same_observation_cannot_create_temporal_confirmation(self):
        self.cue(0)
        for _ in range(10):
            self.scout.update(self.obs)
        self.assertEqual(self.scout.active["samples"], 1)

    def test_already_observed_bearing_cone_does_not_pull_scan_to_its_center(self):
        self.obs["self"]["aim"] = [0, 0]
        self.assertIsNone(self.cue(.3))
        self.assertIsNone(self.scout.active)
        self.assertGreater(self.scout.clusters[0]["rearm"], self.obs["t"])

    def test_unseen_source_is_spent_once_actual_torso_has_looked_at_full_cone(self):
        self.assertIsNotNone(self.cue(.2))
        self.obs["self"]["aim"] = [.4, 0]
        self.obs.update(t=10.1, tick=202, sounds=[])
        self.scout.update(self.obs)
        self.assertIsNone(self.scout.heading(10.1))
        self.assertIsNone(self.scout.active)


def acquisition(initial_yaw, scout_enabled):
    """20 Hz stationary listener versus approaching gun hunter, eight yaw starts.

    Both policies use actual damage bearing for one observation, as the real
    baseline does. A target exists only after actual120-degree FOV entry within
    200m. First outgoing fire is a real readiness/alignment event; its eventual
    hit is deliberately not asserted by this acquisition-only model.
    """
    hello, _ = fixture()
    config = hello["config"]
    scout = SoundScout(config)
    rng = random.Random(23)
    dt = .05
    yaw, pitch = initial_yaw, 0
    target_x = 180.0
    target_speed = config["mech"]["walk_speed"]
    bullets, sound_events, damage_events = [], [], []
    known = False
    first_seen = first_fire = first_impact = None
    first_damage = None
    last_enemy_fire = -1
    action = None
    for step in range(121):
        now = step*dt
        if step % 2 == 0:
            if target_x <= config["vision"]["range"] and abs(angle_error(yaw, 0)) <= math.radians(config["vision"]["fov_deg"])/2:
                known = True
                if first_seen is None:
                    first_seen = now
            heard = [dict(kind=s["kind"], bearing=s["bearing"], dist=s["dist"],
                          age=now-s["at"]) for s in sound_events]
            obs = {"t": now, "tick": step, "sounds": heard,
                   "self": {"aim": [yaw, pitch]}}
            scout.update(obs)
            if known:
                desired = [0, math.atan2(4.5-7, target_x)]
            else:
                cue = scout.heading(now) if scout_enabled else None
                desired = [cue if cue is not None else angle_error(initial_yaw+now*.7, 0), 0]
                if damage_events:
                    desired = [0, 0]
            action = desired
            sound_events, damage_events = [], []
            if known and first_fire is None and abs(angle_error(yaw, 0)) < math.atan2(2.5, target_x) and abs(pitch-desired[1]) < math.atan2(4, target_x):
                first_fire = now
        yaw += max(-config["mech"]["turn_rate"]*dt,
                   min(config["mech"]["turn_rate"]*dt, angle_error(action[0], yaw)))
        yaw = angle_error(yaw, 0)
        pitch += max(-config["mech"]["pitch_rate"]*dt,
                     min(config["mech"]["pitch_rate"]*dt, action[1]-pitch))
        target_x -= target_speed*dt
        if now-last_enemy_fire >= config["weapons"]["gun"]["cooldown"]-1e-8:
            last_enemy_fire = now
            bullets.append(target_x)
            sound_events.append({"kind": "gun", "bearing": rng.gauss(0, math.radians(7)),
                                 "dist": "far" if target_x >= 160 else "mid", "at": now})
        remaining = []
        for x in bullets:
            next_x = x-config["weapons"]["gun"]["speed"]*dt
            # Segment crosses the actual cylinder, so fast rounds cannot tunnel
            # through the player between 50ms samples. Shot height7m is inside9m.
            if next_x <= 2.5 <= x:
                rear = abs(angle_error(yaw, 0)) > math.pi/2
                amount = config["weapons"]["gun"]["damage"]*(1.5 if rear else 1)
                damage_events.append(amount)
                if first_impact is None:
                    contact = (x-2.5)/config["weapons"]["gun"]["speed"]
                    first_impact, first_damage = now+contact, amount
            elif next_x > -2.5:
                remaining.append(next_x)
        bullets = remaining
    return {"seen": first_seen, "fire": first_fire, "impact": first_impact, "damage": first_damage}


class SoundAcquisitionTests(unittest.TestCase):
    def test_real_rear_gun_sound_acquires_before_first_projectile_impact(self):
        before, after = acquisition(math.pi, False), acquisition(math.pi, True)
        self.assertLess(after["seen"], after["impact"])
        self.assertLess(after["seen"], before["seen"])
        self.assertLess(after["fire"], before["fire"])
        self.assertEqual(after["damage"], 45)
        self.assertEqual(before["damage"], 67.5)

    def test_eight_initial_yaws_do_not_delay_existing_real_vision_or_fire(self):
        for i in range(8):
            yaw = angle_error(i*math.tau/8, 0)
            with self.subTest(yaw=yaw):
                before, after = acquisition(yaw, False), acquisition(yaw, True)
                self.assertLessEqual(after["seen"], before["seen"])
                self.assertLessEqual(after["fire"], before["fire"])
                self.assertLessEqual(after["damage"], before["damage"])


if __name__ == "__main__":
    unittest.main()
