"""Ordinary combat should not start at a visible unengaged opponent."""
import math
import unittest

from sentinel.combat import Combat
from sentinel.navigation import Navigator
from sentinel.strategy import Bot
from test_bot import fixture, flat_world


class ActiveThreatTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.bot = Bot(hello)
        self.bot.world = flat_world()
        self.bot.nav = Navigator(self.bot.world, hello["config"]["mech"])
        self.bot.combat = Combat(self.bot.world, hello["config"])
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], hp=1400, max_hp=1400,
                       energy=100, grounded=True, in_zone=True)
        self.enemy = dict(id=1, kind="mech", hp=1400, max_hp=1400, pos=[70, 0, 0],
                          aim=[0, 0], vel=[0, 0, 0], weapons=["gun"])
        self.obs.update(t=100, tick=2000, alive=15, mechs=[self.enemy], projectiles=[],
                        crates=[], pickups=[], cubes=[], drops=[], sounds=[], events=[])
        self.obs["zone"].update(center=[0, 0], next_center=[0, 0], radius=117,
                                next_radius=117, shrink_start=400, shrink_end=500)
        self.me["aim"] = self.bot.combat.solve(self.me, self.enemy, self.me["weapons"][0])[0]

    def test_visible_aim_away_opponent_is_considered_for_safety_but_not_shot(self):
        action = self.bot.act(self.obs)
        self.assertIn(1, self.bot.seen)
        self.assertEqual(action["fire"], [False, False])
        self.assertIsNone(self.bot.duel)

    def test_real_gun_aim_and_prior_damage_allow_self_defense(self):
        self.enemy["aim"] = [math.pi, 0]
        self.assertTrue(self.bot.act(self.obs)["fire"][0])
        self.enemy["aim"] = [0, 0]
        self.obs.update(t=100.1, tick=2002,
                        events=[dict(type="damaged", weapon="gun", amount=45, by=1, bearing=0)])
        self.assertTrue(self.bot.act(self.obs)["fire"][0])
        self.obs.update(t=101, tick=2020, events=[])
        self.assertTrue(self.bot.act(self.obs)["fire"][0])

    def test_finishing_and_last_opponent_can_still_be_engaged(self):
        self.enemy["hp"] = 110
        self.assertTrue(self.bot.act(self.obs)["fire"][0])
        self.enemy["hp"] = 1400
        self.obs["alive"] = 2
        self.assertTrue(self.bot.act(self.obs)["fire"][0])


if __name__ == "__main__":
    unittest.main()
