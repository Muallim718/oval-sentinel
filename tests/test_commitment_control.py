"""Full Bot integration for a focused ready weapon during recovery."""

import copy
import math
import unittest

from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.strategy import Bot
from test_bot import fixture, flat_world


class FinishControlTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.config = hello["config"]
        self.bot = Bot(hello)
        self.world = flat_world()
        self.bot.world = self.world
        self.bot.combat = Combat(self.world, self.config)
        self.bot.nav = Navigator(self.world, self.config["mech"])
        self.bot.cover = CoverPlanner(self.world, self.config)
        self.bot.motion = GroundSteering(self.world, self.config)
        self.me = self.obs["self"]
        self.me.update(pos=[-30, 0, 0], vel=[0, 0, 0], hp=780, energy=100, in_zone=True)
        self.enemy = {"id": (self.me["id"]+1)%16, "kind": "mech", "pos": [35, 0, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 200,
                      "max_hp": 1400, "weapons": ["gun"], "cubes": 0}
        self.obs.update(t=100, tick=2000, alive=12, mechs=[self.enemy], events=[],
                        projectiles=[], crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=115, next_center=[0, 0], next_radius=115,
                                shrink_start=500, shrink_end=550)
        self.me["weapons"][0].update(ammo=8, cooldown=0, reload=0)

    def laser(self, charge):
        return {"kind": "laser", "charge": charge, "cooldown": 0,
                "stats": copy.deepcopy(self.config["weapons"]["laser"])}

    def aim_at_enemy(self, slot):
        aim, _, _, _ = self.bot.combat.solve(self.me, self.enemy, self.me["weapons"][slot])
        self.me["aim"] = aim

    def seed_observed_gun_hits(self):
        for index, elapsed in enumerate((.7, .45, .2)):
            old = dict(self.obs, t=100-elapsed, tick=1980+index*5)
            old["events"] = [{"type": "hit", "weapon": "gun", "amount": 45,
                              "target": self.enemy["id"]}]
            self.bot.finish.update(old)

    def test_ready_gun_finishes_without_starting_by_stander_laser_charge(self):
        self.me["weapons"][1] = self.laser(0)
        self.seed_observed_gun_hits()
        self.aim_at_enemy(0)
        action = self.bot.act(self.obs)
        self.assertTrue(self.bot.recovering)
        self.assertEqual(self.bot.finish.weapon_kind, "gun")
        self.assertEqual(action["fire"], [True, False])

    def test_ready_partial_laser_releases_when_its_damage_can_finish(self):
        self.enemy["hp"] = 180
        self.me["weapons"][1] = self.laser(.4)
        self.aim_at_enemy(1)
        action = self.bot.act(self.obs)
        self.assertEqual(self.bot.finish.weapon_kind, "laser")
        self.assertEqual(action["fire"], [False, False])

    def test_second_exposed_shooter_vetoes_temporary_finishing_control(self):
        self.seed_observed_gun_hits()
        self.aim_at_enemy(0)
        self.obs["mechs"].append({**self.enemy, "id": (self.me["id"]+2)%16,
                                  "pos": [5, 20, 0], "hp": 1400})
        action = self.bot.act(self.obs)
        self.assertEqual(self.bot.mode, "recover")
        self.assertIsNone(self.bot.finish.target_id)
        self.assertEqual(action["fire"], [False, False])


if __name__ == "__main__":
    unittest.main()
