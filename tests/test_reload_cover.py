"""A reload detour is allowed only while the gun cannot fight."""
import copy
import unittest

from sentinel.cover import CoverPlanner, firing_lane
from sentinel.reload_cover import ReloadCover
from test_bot import fixture, flat_world, rectangle


class ReloadCoverTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.config = hello["config"]
        self.world = flat_world([rectangle(-3, -20, 3, 20)])
        self.shelter = CoverPlanner(self.world, self.config)
        self.policy = ReloadCover(self.config)
        self.me = self.obs["self"]
        self.me.update(pos=[-10, -26, 0], vel=[0, 0, 0], hp=1200,
                       max_hp=1400, grounded=True, in_zone=True)
        self.enemy = dict(id=3, kind="mech", pos=[45, -26, 0], cubes=0)
        self.obs.update(t=101, mechs=[self.enemy])
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=0, reload=2.2)

    def choose(self, threats=None):
        return self.policy.choose(self.obs, self.enemy, threats or [(self.enemy, 1)],
                                  ((0, 0), 100), self.shelter)

    def test_moves_to_real_screen_then_releases_on_refill(self):
        self.assertTrue(firing_lane(self.world, self.config, self.me["pos"], self.me, self.enemy)[0])
        plan = self.choose()
        self.assertIsNotNone(plan)
        self.assertGreater(plan.move[1], 0)
        self.assertFalse(firing_lane(self.world, self.config, plan.goal, self.me, self.enemy)[0])
        self.obs["t"] += 1
        self.gun["reload"] = 1.2
        self.me["pos"] = list(plan.goal)
        self.assertEqual(self.choose().move, (0, 0))
        self.gun.update(ammo=12, reload=0)
        self.assertIsNone(self.choose())
        self.assertIsNone(self.policy.target_id)

    def test_short_reload_or_a_ready_laser_keeps_ordinary_control(self):
        self.gun["reload"] = .45
        self.assertIsNone(self.choose())
        self.gun["reload"] = 2.2
        self.me["weapons"][1] = dict(kind="laser", charge=0, cooldown=0,
                                     stats=copy.deepcopy(self.config["weapons"]["laser"]))
        self.assertIsNone(self.choose())

    def test_new_hunter_or_lost_ballistic_shield_cancels(self):
        self.assertIsNotNone(self.choose())
        second = dict(self.enemy, id=4, pos=[-48, -26, 0])
        self.assertIsNone(self.choose([(self.enemy, 1), (second, 1)]))
        self.assertIsNotNone(self.choose())
        self.enemy["pos"] = [-59, -26, 0]
        self.assertIsNone(self.choose())

    def test_does_not_make_up_cover_or_leave_zone(self):
        bare = CoverPlanner(flat_world(), self.config)
        self.assertIsNone(self.policy.choose(self.obs, self.enemy, [(self.enemy, 1)], ((0, 0), 100), bare))
        self.me["in_zone"] = False
        self.assertIsNone(self.choose())


if __name__ == "__main__":
    unittest.main()
