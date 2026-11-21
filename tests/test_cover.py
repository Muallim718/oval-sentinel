"""Ground shelter and commitment tests; these do not simulate scored matches."""
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.cover import CoverPlanner, firing_lane
from sentinel.geometry import distance


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-8, 18, 0], hp=700, vel=[0, 0, 0])
        self.enemy = {"id": 1, "kind": "mech", "pos": [35, 0, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                      "max_hp": 1400, "weapons": ["gun"]}
        self.circle = ([0, 0], 118)
        self.world = flat_world([rectangle(-2, -20, 2, 20)])
        self.planner = CoverPlanner(self.world, self.hello["config"])

    def choose(self, enemies=None, recovering=True):
        return self.planner.choose(self.obs, [(e, 1) for e in (enemies or [self.enemy])],
                                   self.circle, recovering)

    def test_holds_existing_ground_shelter_instead_of_orbiting_away(self):
        goal = self.choose()
        self.assertEqual(goal, (-8, 18))
        self.assertEqual(self.planner.state, "holding")
        self.assertTrue(self.planner.sheltered)
        self.assertLessEqual(self.planner.rays, 4)

    def test_finds_wall_side_shelter_when_exposed_near_corner(self):
        self.me["pos"] = [-8, 36, 0]
        goal = None
        for _ in range(8):
            goal = self.choose()
            if goal:
                break
        self.assertIsNotNone(goal)
        self.assertEqual(self.planner.state, "approach")
        point = [*goal, self.world.ground(*goal)]
        self.assertTrue(self.world.body_clear(*point, self.me["stats"]["radius"]+.5,
                                              self.me["stats"]["height"]))
        self.assertFalse(self.world.line_clear([35, 0, 7], [*goal, 8.55]))

    def test_committed_cover_does_not_thrash_between_equivalent_wall_sides(self):
        self.me["pos"] = [-8, 36, 0]
        goal = self.choose()
        self.assertIsNotNone(goal)
        self.enemy["pos"][1] += .2
        self.me["pos"][0] -= .2
        self.assertEqual(self.choose(), goal)
        self.assertEqual(self.planner.state, "approach")

    def test_enemy_rounding_corner_invalidates_held_refuge(self):
        old = self.choose()
        self.enemy["pos"] = [-25, 30, 0]
        goal = self.choose()
        self.assertNotEqual(goal, old)
        self.assertFalse(self.planner.sheltered)
        self.assertNotEqual(self.planner.state, "holding")

    def test_zone_shrink_invalidates_previously_safe_cover(self):
        old = self.choose()
        self.circle = ([40, 0], 30)
        goal = self.choose()
        self.assertNotEqual(goal, old)
        if goal:
            self.assertLess(distance(goal, self.circle[0]), self.circle[1])

    def test_live_growth_rechecks_wall_clearance(self):
        self.me["pos"] = [-8, 36, 0]
        old = self.choose()
        self.assertIsNotNone(old)
        self.me["stats"]["radius"] = 8
        self.me["stats"]["height"] = 18
        goal = self.choose()
        self.assertNotEqual(goal, old)
        if goal:
            self.assertTrue(self.world.body_clear(*goal, 0, radius=8.5, height=18))

    def test_multiple_firing_lanes_cannot_be_called_sheltered(self):
        second = {**self.enemy, "id": 2, "pos": [-55, 18, 0]}
        self.choose([self.enemy, second])
        self.assertFalse(self.planner.sheltered)
        self.assertNotEqual(self.planner.state, "holding")

    def test_fifth_exposed_enemy_vetoes_holding_behind_four_blocked_enemies(self):
        first_four = [{**self.enemy, "id": i, "pos": [35+i, 0, 0]} for i in range(4)]
        fifth = {**self.enemy, "id": 5, "pos": [-95, 18, 0]}
        self.choose(first_four)
        self.assertTrue(self.planner.sheltered)
        self.choose(first_four+[fifth])
        self.assertFalse(self.planner.sheltered)
        self.assertNotEqual(self.planner.state, "holding")

    def test_failed_route_rejection_skips_nearby_anchor_until_expiry(self):
        self.me["pos"] = [-8, 36, 0]
        old = self.choose()
        self.assertIsNotNone(old)
        self.planner.reject(old, self.obs["t"], seconds=8)
        self.assertIsNone(self.planner.goal)
        for _ in range(4):
            goal = self.choose()
            if goal:
                self.assertGreaterEqual(distance(goal, old), 3)
        self.obs["t"] += 8
        self.planner.goal = old  # retry the previously unreachable route
        self.assertEqual(self.choose(), old)

    def test_rejected_anchor_does_not_block_holding_actual_safe_position(self):
        self.planner.reject(self.me["pos"], self.obs["t"])
        self.assertEqual(self.choose(), tuple(self.me["pos"][:2]))
        self.assertEqual(self.planner.state, "holding")

    def test_low_cover_does_not_hide_exposed_head(self):
        self.planner = CoverPlanner(flat_world([rectangle(-2, -20, 2, 20, top=6)]),
                                    self.hello["config"])
        self.choose()
        self.assertFalse(self.planner.sheltered)

    def test_center_hidden_at_corner_does_not_hide_exposed_cylinder_flank(self):
        wall = flat_world([rectangle(-3, -45, 3, 45, top=20)])
        self.me["pos"] = [-13.5026, -41.6013, 0]
        self.enemy["pos"] = [29.85, -53.94, 0]
        origin = [29.85, -53.94, 7]
        self.assertFalse(wall.line_clear(origin, [-13.5026, -41.6013, 4.5]))
        self.assertFalse(wall.line_clear(origin, [-13.5026, -41.6013, 8.55]))
        exposed, rays = firing_lane(wall, self.hello["config"], self.me["pos"],
                                     self.me, self.enemy)
        self.assertTrue(exposed)
        self.assertGreater(rays, 2)
        self.planner = CoverPlanner(wall, self.hello["config"])
        self.choose()
        self.assertFalse(self.planner.sheltered)
        self.assertNotEqual(self.planner.state, "holding")

    def test_near_pursuer_promotes_farther_protected_wall_anchor(self):
        self.world = flat_world([rectangle(-3, -60, 3, 60, top=20)])
        self.planner = CoverPlanner(self.world, self.hello["config"])
        self.me["pos"] = [-8, 45, 0]
        self.enemy["pos"] = [16, 30, 0]
        original_distance = distance(self.me["pos"], self.enemy["pos"])
        goal = None
        for _ in range(8):
            goal = self.choose()
            if goal and distance(goal, self.me["pos"]) > 3:
                break
        self.assertTrue(self.planner.sheltered)
        self.assertEqual(self.planner.state, "approach")
        self.assertGreater(distance(goal, self.enemy["pos"]), original_distance+10)
        exposed, _ = firing_lane(self.world, self.hello["config"], [*goal, 0],
                                  self.me, self.enemy)
        self.assertFalse(exposed)

    def test_near_pursuer_does_not_force_abandoning_only_actual_protection(self):
        self.enemy["pos"] = [16, 0, 0]
        for _ in range(8):
            self.assertEqual(self.choose(), tuple(self.me["pos"][:2]))
            self.assertTrue(self.planner.sheltered)
            self.assertEqual(self.planner.state, "holding")

    def test_clear_same_side_approach_beats_shorter_building_detour(self):
        self.world = flat_world([rectangle(-3, -45, 3, 45, top=20)])
        self.planner = CoverPlanner(self.world, self.hello["config"])
        self.me["pos"] = [25, 60, 0]
        self.enemy["pos"] = [75, 0, 0]
        blocked, clear = (-8, 30), (-35, 55)
        self.assertLess(distance(self.me["pos"], blocked), distance(self.me["pos"], clear))
        self.assertFalse(self.world.walk_clear(self.me["pos"], [*blocked, 0]))
        self.assertTrue(self.world.walk_clear(self.me["pos"], [*clear, 0]))
        self.planner._anchors = lambda me: [blocked, clear]
        self.assertEqual(self.choose(), clear)

    def test_blocked_direct_approach_remains_available_when_it_is_only_shelter(self):
        self.world = flat_world([rectangle(-3, -45, 3, 45, top=20)])
        self.planner = CoverPlanner(self.world, self.hello["config"])
        self.me["pos"] = [25, 60, 0]
        self.enemy["pos"] = [75, 0, 0]
        blocked = (-8, 30)
        self.assertFalse(self.world.walk_clear(self.me["pos"], [*blocked, 0]))
        self.planner._anchors = lambda me: [blocked]
        self.assertEqual(self.choose(), blocked)

    def test_open_field_without_better_wall_cover_returns_none(self):
        self.planner = CoverPlanner(flat_world(), self.hello["config"])
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "idle")

    def test_no_observed_threats_releases_cover(self):
        self.choose()
        self.assertIsNone(self.planner.choose(self.obs, [], self.circle, True))
        self.assertIsNone(self.planner.goal)
        self.assertEqual(self.planner.state, "idle")

    def test_airborne_mech_does_not_claim_shelter_on_ground_below(self):
        self.me["pos"][2] = 28
        self.choose()
        self.assertFalse(self.planner.sheltered)
        self.assertNotEqual(self.planner.state, "holding")

    def test_search_work_is_bounded_and_public_map_initializes(self):
        real = CoverPlanner(CoverTests.real_world(), self.hello["config"])
        self.assertGreater(len(real.sites), 0)
        self.me["pos"] = [-8, 36, 0]
        self.choose()
        self.assertLessEqual(self.planner.evaluations, self.planner.MAX_ANCHORS+2)
        self.assertLessEqual(self.planner.rays, (self.planner.MAX_ANCHORS+2)*16)

    @staticmethod
    def real_world():
        from sentinel.geometry import World
        hello, _ = fixture()
        return World(hello["map"]["dir"])


if __name__ == "__main__":
    unittest.main()
