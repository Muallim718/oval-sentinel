"""Measured corner geometry and laser ownership, not a scored-match model."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.ambush import AmbushPlanner
from sentinel.cover import firing_lane
from sentinel.geometry import distance


class AmbushTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-6.3, -38.5, 0], vel=[0, 0, 0], aim=[0, 0],
                       hp=1400, max_hp=1400, energy=100, grounded=True, in_zone=True)
        self.laser = {"kind": "laser", "cooldown": 0, "charge": 0,
                      "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.me["weapons"][1] = self.laser
        self.enemy = {"id": 1, "kind": "mech", "pos": [100, -52, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                      "max_hp": 1400, "weapons": ["gun"], "charging": False}
        self.obs.update(t=10, tick=200, mechs=[self.enemy], beams=[], projectiles=[], events=[])
        self.circle = ([0, 0], 118)
        self.world = flat_world([rectangle(-3, -45, 3, 45)])
        self.planner = AmbushPlanner(self.world, self.hello["config"])

    def choose(self, enemies=None, recovering=False):
        return self.planner.choose(self.obs, [(e, 1) for e in (enemies or [self.enemy])],
                                   self.circle, recovering=recovering)

    def aligned(self):
        self.me["aim"] = self.planner._aim(self.me["pos"], self.me, self.enemy)[0]

    def peek(self):
        self.assertIsNotNone(self.choose())
        self.laser["charge"] = .75
        self.obs["t"] += .75
        action = self.choose()
        self.assertEqual(self.planner.state, "peek")
        return action

    def test_pair_has_full_body_shelter_clear_corridor_and_firing_ray(self):
        action = self.choose()
        self.assertIsNotNone(action)
        self.assertFalse(firing_lane(self.world, self.hello["config"], self.planner.hide,
                                     self.me, self.enemy)[0])
        self.assertTrue(self.planner._walk(self.planner.hide, self.planner.peek, self.me))
        self.assertTrue(self.planner._can_shoot(self.planner.peek, self.me, self.enemy, self.laser))
        self.assertLessEqual(self.planner.candidates, 12)
        self.assertLess(distance(self.planner.hide, self.planner.peek), 14)

    def test_can_charge_behind_wall_even_when_normal_combat_has_no_solution(self):
        action = self.choose()
        self.assertFalse(self.planner._can_shoot(self.me["pos"], self.me, self.enemy, self.laser))
        self.assertEqual(self.planner.state, "charge")
        self.assertEqual(action["move"], [0., 0.])
        self.assertEqual(action["fire"], [False, True])
        self.laser["charge"] = .5
        self.obs["t"] += .5
        self.assertEqual(self.choose()["fire"], [False, True])
        self.assertEqual(self.planner.state, "charge")

    def test_full_charge_peek_owns_boost_and_motion_despite_exposure(self):
        action = self.peek()
        self.assertTrue(action["boost"])
        self.assertTrue(action["fire"][1])
        self.assertLess(action["move"][1], -.5)

    def test_last_meters_of_approach_are_owned_to_avoid_arrival_band_stall(self):
        self.me["pos"] = [-8.4, -38.5, 0]
        action = self.choose()
        self.assertEqual(self.planner.state, "approach")
        self.assertIsNotNone(action["move"])
        self.assertGreater(action["move"][0], 0)
        self.assertEqual(action["fire"], [False, False])

    def test_farther_approach_uses_normal_navigation(self):
        self.me["pos"] = [-12, -39, 0]
        action = self.choose()
        self.assertEqual(self.planner.state, "approach")
        self.assertIsNone(action["move"])

    def test_never_release_merely_because_requested_aim_is_correct(self):
        self.peek()
        self.me["pos"] = list(self.planner.peek)
        self.me["aim"] = [math.pi/2, 0]
        self.laser["charge"] = 1.3
        self.obs["t"] += .6
        action = self.choose()
        self.assertTrue(action["fire"][1])
        self.assertEqual(self.planner.state, "peek")

    def test_clear_aligned_full_beam_releases_then_waits_for_observed_reset(self):
        self.peek()
        self.me["pos"] = list(self.planner.peek)
        self.aligned()
        self.laser["charge"] = 1.3
        self.obs["t"] += .6
        action = self.choose()
        self.assertEqual(self.planner.state, "release")
        self.assertEqual(action["fire"], [False, False])
        self.assertEqual(action["move"], [0., 0.])
        self.obs["t"] += .1
        self.assertEqual(self.choose()["move"], [0., 0.])
        self.laser.update(charge=0, cooldown=1.55)
        self.obs["t"] += .1
        action = self.choose()
        self.assertEqual(self.planner.state, "retreat")
        self.assertGreater(action["move"][1], .5)
        self.assertFalse(any(action["fire"]))

    def test_retreat_finishes_with_cooldown_behind_verified_shelter(self):
        self.peek()
        self.planner._withdraw(self.obs, "return behind cover after beam")
        self.laser.update(charge=0, cooldown=1.4)
        self.me["pos"] = list(self.planner.hide)
        action = self.choose()
        self.assertEqual(self.planner.state, "cooldown")
        self.assertFalse(any(action["fire"]))
        self.assertEqual(action["move"], [0., 0.])

    def test_close_hunter_does_not_start_cycle_it_can_round_before_completion(self):
        self.enemy["pos"] = [35, -52, 0]
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "idle")

    def test_charging_opponent_denies_peek_and_avoids_automatic_release_deadline(self):
        self.choose()
        self.enemy.update(charging=True, weapons=["gun", "laser"])
        self.laser["charge"] = .75
        self.obs["t"] += .75
        action = self.choose()
        self.assertEqual(self.planner.state, "charge")
        self.assertTrue(action["fire"][1])
        self.laser["charge"] = 2.55
        self.obs["t"] += 1.8
        action = self.choose()
        self.assertEqual(self.planner.state, "idle")
        self.assertIsNone(action)

    def test_second_exposed_lane_rejects_pair_even_when_target_is_behind_wall(self):
        other = {**self.enemy, "id": 2, "pos": [-95, -30, 0]}
        self.obs["mechs"].append(other)
        self.assertIsNone(self.choose([self.enemy, other]))

    def test_zone_or_body_change_cannot_preserve_old_pair(self):
        self.choose()
        self.circle = ([0, 50], 30)
        self.assertIsNone(self.choose())
        self.assertTrue(self.planner.needs_escape)
        self.assertEqual(self.planner.state, "idle")
        self.setUp()
        self.choose()
        self.me["stats"]["radius"] = 5
        self.assertIsNone(self.choose())
        self.assertTrue(self.planner.needs_escape)

    def test_healing_and_energy_reserve_veto_optional_trade(self):
        self.assertIsNone(self.choose(recovering=True))
        self.me["energy"] = 45
        self.assertIsNone(self.choose())

    def test_lost_current_tracking_returns_from_exposure_and_then_releases_control(self):
        self.peek()
        self.me["pos"] = list(self.planner.peek)
        self.laser["charge"] = 1.1
        self.obs["t"] += 1.1
        self.obs["mechs"] = []
        action = self.choose()
        self.assertEqual(self.planner.state, "retreat")
        self.assertGreater(action["move"][1], 0)
        self.assertFalse(any(action["fire"]))
        self.assertTrue(self.planner.needs_escape)

    def test_full_capped_charge_still_has_a_local_automatic_release_deadline(self):
        self.choose()
        self.enemy.update(charging=True, weapons=["gun", "laser"])
        self.laser["charge"] = .75  # Never grows after reaching full.
        self.obs["t"] += .8
        self.assertIsNotNone(self.choose())
        self.assertEqual(self.planner.state, "charge")
        self.obs["t"] = 12.5
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "idle")
        self.assertLess(self.obs["t"], 10+.75+2)

    def test_kill_or_missing_threat_list_does_not_hand_off_exposed_legs(self):
        for killed in (False, True):
            with self.subTest(killed=killed):
                self.setUp()
                self.peek()
                self.me["pos"] = list(self.planner.peek)
                self.laser.update(charge=0, cooldown=1.5)
                self.obs["t"] += 1.1
                self.obs["mechs"] = []
                self.obs["events"] = [{"type": "kill", "target": 1}] if killed else []
                action = self.planner.choose(self.obs, [], self.circle)
                self.assertIsNotNone(action)
                self.assertEqual(self.planner.state, "retreat")
                self.assertGreater(action["move"][1], 0)
                self.assertFalse(any(action["fire"]))
                self.me["pos"] = list(self.planner.hide)
                self.me["vel"] = [0, 0, 0]
                self.obs["t"] += .1
                self.assertIsNone(self.planner.choose(self.obs, [], self.circle))
                self.assertEqual(self.planner.state, "idle")


if __name__ == "__main__":
    unittest.main()
