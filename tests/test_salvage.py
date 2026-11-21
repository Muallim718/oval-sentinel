"""Verified-kill reward commitment with live health, pickup races, and growth."""
import copy
import math
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.salvage import KillSalvage


class KillSalvageTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[-30, 0, 0], vel=[0, 0, 0], hp=650, energy=100,
                       aim=[0, 0], grounded=True, in_zone=True, cubes=0)
        self.obs.update(t=10, tick=200, cubes=[], mechs=[], projectiles=[], events=[])
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0], next_radius=118,
                                shrink_start=500, shrink_end=550)
        self.victim = {"id": 1, "kind": "mech", "pos": [-15, 0, 0], "cubes": 3}
        self.hunter = {"id": 2, "kind": "mech", "pos": [80, 0, 0], "vel": [-11.7, 0, 0],
                       "weapons": ["gun"], "hp": 1400}
        self.cubes = [{"id": 5000+i, "pos": [-15, (i-2)*.2, 0]} for i in range(5)]
        self.obs["cubes"] = self.cubes
        self.salvage = KillSalvage(self.world, self.hello["config"])
        self.salvage.record_kill(10, 1, (9.9, self.victim))
        self.circle = ([0, 0], 118)

    def choose(self, threats=None):
        if threats is None:
            threats = [(self.hunter, 1)]
        return self.salvage.choose(self.obs, self.cubes, threats, self.circle)

    def test_recovering_exposed_five_cube_reward_wins_health_and_arrival_budgets(self):
        goal = self.choose()
        self.assertIsNotNone(goal)
        self.assertTrue(self.salvage.active)
        self.assertTrue(self.salvage.sprint)
        self.assertAlmostEqual(self.salvage.risk["healing"], 280)
        self.assertGreater(self.salvage.risk["remaining_hp"], 350)
        self.assertGreaterEqual(self.salvage.risk["escape_energy"], 30)

    def test_nearby_threat_under95m_does_not_blanket_veto_viable_reward(self):
        self.hunter["pos"] = [35, 55, 0]
        self.assertLess(math.dist(self.me["pos"], self.hunter["pos"]), 95)
        self.assertIsNotNone(self.choose())

    def test_no_actual_known_cube_means_no_invented_loot_goal(self):
        self.cubes = self.obs["cubes"] = []
        self.assertIsNone(self.choose())
        self.assertFalse(self.salvage.active)

    def test_cube_without_verified_kill_is_ordinary_loot_not_special_salvage(self):
        self.salvage.beacons = []
        self.assertIsNone(self.choose())

    def test_closer_hunter_wins_race_and_aborts_existing_commitment(self):
        self.assertIsNotNone(self.choose())
        self.hunter["pos"] = [-8, 0, 0]
        self.assertIsNone(self.choose())
        self.assertIn("race", self.salvage.reason)
        self.assertIsNone(self.salvage.active_cube)

    def test_incoming_volley_can_overwhelm_cube_healing_and_abort(self):
        self.me["hp"] = 400
        self.obs["projectiles"] = [{"id": 2000+i, "kind": "gun", "pos": [-20+i*.05, 0, 7],
                                     "vel": [-252, 0, 0]} for i in range(6)]
        self.assertIsNone(self.choose())
        self.assertLess(self.salvage.risk["remaining_hp"], 350)

    def test_future_growth_cannot_trap_bot_in_narrow_pickup_corridor(self):
        self.world = flat_world([rectangle(-15, -30, 15, -3.1), rectangle(-15, 3.1, 15, 30)])
        self.salvage = KillSalvage(self.world, self.hello["config"])
        self.victim["pos"] = [0, 0, 0]
        self.salvage.record_kill(10, self.victim)
        self.cubes = self.obs["cubes"] = [{"id": 5000+i, "pos": [0, (i-2)*.1, 0]} for i in range(5)]
        self.assertIsNone(self.choose([]))
        self.assertIn("body", self.salvage.reason)

    def test_wall_or_predicted_zone_blocks_salvage_route(self):
        self.world = flat_world([rectangle(-24, -20, -21, 20)])
        self.salvage = KillSalvage(self.world, self.hello["config"])
        self.salvage.record_kill(10, self.victim)
        self.assertIsNone(self.choose([]))
        self.salvage = KillSalvage(flat_world(), self.hello["config"])
        self.salvage.record_kill(10, self.victim)
        self.circle = ([70, 0], 20)
        self.assertIsNone(self.choose([]))
        self.assertIn("zone", self.salvage.reason)

    def test_commitment_retains_same_actual_cube_while_conditions_stay_viable(self):
        first = self.choose()
        self.obs["t"] += .1
        self.cubes.reverse()
        self.assertEqual(self.choose(), first)
        self.assertEqual(self.salvage.state, "collect")

    def test_expired_kill_and_stale_negative_cube_observation_do_not_persist(self):
        self.obs["t"] = 19
        self.assertIsNone(self.choose())
        self.obs["t"] = 10
        self.salvage.record_kill(10, self.victim)
        self.me["pos"] = [-16, 0, 0]
        self.obs["cubes"] = []
        self.assertIsNone(self.choose([]))

    def test_emergency_and_insufficient_budget_fail_closed(self):
        self.assertIsNotNone(self.choose())
        self.assertIsNone(self.salvage.choose(self.obs, self.cubes, [], self.circle, emergency=True))
        self.assertIsNone(self.salvage.active_cube)
        self.salvage.SEARCH_SECONDS = 0
        self.assertIsNone(self.choose([]))

    def test_late_window_cannot_start_a_route_that_will_expire_before_pickup(self):
        self.obs["t"] = 17.2
        self.assertIsNone(self.choose([]))
        self.assertIn("expires", self.salvage.reason)

    def test_dead_victim_is_not_a_live_pickup_racer(self):
        self.assertIsNotNone(self.choose([(self.victim, 1)]))


if __name__ == "__main__":
    unittest.main()
