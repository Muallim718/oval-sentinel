"""Audio can orient the camera without authorizing an unseen shot."""

import math
import unittest

from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.geometry import angle_error
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.strategy import Bot
from test_bot import fixture, flat_world


class ContactControlTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.bot = Bot(hello)
        world, config = flat_world(), hello["config"]
        self.bot.world = world
        self.bot.combat = Combat(world, config)
        self.bot.cover = CoverPlanner(world, config)
        self.bot.motion = GroundSteering(world, config)
        self.bot.nav = Navigator(world, config["mech"])
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], aim=[0, 0], hp=1400,
                       energy=100, grounded=True, in_zone=True)
        self.obs.update(t=65, tick=1300, alive=16, events=[], projectiles=[], mechs=[],
                        crates=[], cubes=[], pickups=[], drops=[], offer=None,
                        sounds=[{"kind": "gun", "bearing": 3.0, "dist": "far", "age": 0}])
        self.obs["zone"].update(center=[0, 0], radius=115, next_center=[0, 0],
                                next_radius=115, shrink_start=600, shrink_end=650)

    def test_unseen_gun_sound_turns_only_the_torso(self):
        answer = self.bot.act(self.obs)
        self.assertLess(abs(angle_error(answer["aim"][0], 3.0)), .01)
        self.assertEqual(answer["fire"], [False, False])
        self.assertFalse(self.bot.seen)

    def test_real_visible_enemy_retains_combat_aim_over_contradictory_audio(self):
        self.obs["mechs"] = [{"id": (self.me["id"]+1)%16, "kind": "mech", "pos": [90, 0, 0],
                              "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                              "max_hp": 1400, "cubes": 0, "weapons": ["gun"]}]
        answer = self.bot.act(self.obs)
        self.assertLess(abs(angle_error(answer["aim"][0], 0)), .01)


if __name__ == "__main__":
    unittest.main()
