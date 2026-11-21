"""Early pressure is an evidence filter, never a house-role detector."""
import copy
import math
import unittest

from test_bot import fixture
from sentinel.pressure import EarlyPressure


class PressureTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.obs.update(t=10, tick=200, alive=16, beams=[], events=[], projectiles=[])
        self.obs["self"].update(pos=[0, 0, 0], vel=[0, 0, 0])
        self.hunter = {"id": 1, "kind": "mech", "pos": [100, 0, 0],
                       "vel": [-8, 0, 0], "aim": [math.pi, 0], "charging": False}
        self.first = {"id": 2, "kind": "mech", "pos": [120, 80, 0],
                      "vel": [0, 0, 0], "aim": [0, 0], "charging": False}
        self.second = {"id": 3, "kind": "mech", "pos": [130, -80, 0],
                       "vel": [0, 0, 0], "aim": [0, 0], "charging": False}
        self.obs["mechs"] = [self.hunter, self.first, self.second]
        self.pressure = EarlyPressure(hello["config"])

    def sample(self, seconds=.7):
        result = None
        for _ in range(round(seconds/.1)+1):
            result = self.pressure.credible(self.obs, self.obs["mechs"])
            self.obs["t"] = round(self.obs["t"]+.1, 6)
            self.obs["tick"] += 2
        return result

    def test_new_observations_keep_all_until_continuous_evidence_supports_one(self):
        enemies = self.obs["mechs"]
        self.assertEqual(self.pressure.credible(self.obs, enemies), enemies)
        self.assertEqual(self.sample(.3), enemies)
        result = self.sample(.4)
        self.assertEqual(result, [self.hunter])
        self.assertIs(result[0], self.hunter)
        self.assertEqual(self.pressure.ignored, {2, 3})

    def test_zero_or_multiple_credible_attackers_never_filter_the_scene(self):
        self.sample()
        self.first["aim"] = [math.atan2(-80, -120), 0]
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertFalse(self.pressure.ignored)
        self.setUp()
        self.hunter.update(aim=[0, 0], vel=[0, 0, 0])
        self.assertEqual(self.sample(), self.obs["mechs"])
        self.assertFalse(self.pressure.ignored)

    def test_turn_restores_immediately_even_while_still_pointing_away(self):
        self.assertEqual(self.sample(), [self.hunter])
        self.first["aim"][0] += .04  # Remains far outside the towards-us cone.
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertFalse(self.pressure.passer(self.first, self.obs["self"], self.obs["t"]))

    def test_near_charging_and_enemy_closing_each_restore_immediately(self):
        changes = (
            lambda: self.first.update(pos=[70, 0, 0]),
            lambda: self.first.update(charging=True),
            lambda: self.first.update(vel=[-6, -4, 0]),
        )
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                self.assertEqual(self.sample(), [self.hunter])
                change()
                self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.setUp()
        self.assertEqual(self.sample(), [self.hunter])
        self.obs["self"]["vel"] = [8, 0, 0]
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), [self.hunter])

    def test_attributed_damage_and_beam_keep_attack_lane_for_five_seconds(self):
        for evidence in ("hit", "beam"):
            with self.subTest(evidence=evidence):
                self.setUp()
                self.sample()
                attack_time = self.obs["t"]
                if evidence == "hit":
                    self.obs["events"] = [{"type": "damaged", "by": 2, "weapon": "gun", "amount": 45}]
                else:
                    self.obs["beams"] = [{"kind": "laser", "by": 2, "age": .05, "path": []}]
                self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
                self.obs["events"] = self.obs["beams"] = []
                self.obs["t"] = attack_time+4.9
                self.obs["tick"] += 98
                self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
                self.obs["t"] = attack_time+5.1
                self.obs["tick"] += 4
                self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
                self.assertEqual(self.sample(.7), [self.hunter])

    def test_early_guard_expires_without_preserving_a_discount(self):
        self.assertEqual(self.sample(), [self.hunter])
        self.obs["alive"] = 11
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertFalse(self.pressure.history)
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.obs["alive"] = 12
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.obs["t"] = 75.1
        self.obs["tick"] += 1300
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertFalse(self.pressure.eligible)

    def test_missing_observation_or_long_gap_requires_a_fresh_streak(self):
        self.assertEqual(self.sample(), [self.hunter])
        self.obs["t"] += .5
        self.obs["tick"] += 10
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertEqual(self.sample(), [self.hunter])
        self.obs["mechs"] = [self.hunter, self.second]
        self.pressure.update(self.obs)
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.obs["mechs"] = [self.hunter, self.first, self.second]
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])

    def test_a_new_visible_bullet_near_passer_firing_lane_restores_before_damage(self):
        self.first["pos"] = [120, 0, 0]
        self.assertEqual(self.sample(), [self.hunter])
        self.obs["projectiles"] = [{"id": 201, "kind": "gun", "pos": [110, 0, 7],
                                     "vel": [-252, 0, 0]}]
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        self.assertIn(2, self.pressure.attacked_at)

    def test_missing_fields_unknown_enemy_and_repeated_same_tick_fail_closed(self):
        self.assertEqual(self.sample(), [self.hunter])
        fresh = copy.deepcopy(self.first)
        fresh["id"] = 4
        self.obs["mechs"].append(fresh)
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])
        # Repeated callers cannot accumulate invented observation time.
        for _ in range(20):
            self.pressure.update(self.obs)
        self.assertFalse(self.pressure.passer(fresh, self.obs["self"], self.obs["t"]))
        self.first.pop("aim")
        self.obs["t"] += .1
        self.obs["tick"] += 2
        self.assertEqual(self.pressure.credible(self.obs, self.obs["mechs"]), self.obs["mechs"])


if __name__ == "__main__":
    unittest.main()
