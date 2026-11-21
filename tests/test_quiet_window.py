"""Movement ownership must not silently revoke a valid hostile weapon action."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.quiet_window import QuietWindow
from sentinel.strategy import Bot


class QuietWindowTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-70, 0, 0], vel=[0, 0, 0], hp=700, max_hp=1400,
                       aim=[0, 0], grounded=True, in_zone=True, cubes=0)
        self.me["weapons"][0].update(ammo=12, cooldown=0, reload=0)
        self.enemy = dict(id=1, kind="mech", pos=[0, 0, 0], vel=[0, 0, 0],
                          aim=[math.pi, 0], hp=1400, max_hp=1400,
                          cubes=0, weapons=["gun"], charging=False)
        self.obs.update(t=10, tick=200, alive=16, mechs=[self.enemy], events=[],
                        projectiles=[], crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.window = QuietWindow(self.hello["config"])

    def decide(self, sheltered=False):
        self.window.update(self.obs)
        return self.window.repair(self.obs, sheltered=sheltered)

    def bot(self, world=None):
        bot = Bot(self.hello)
        world = world or flat_world()
        bot.world = world
        bot.nav = Navigator(world, self.hello["config"]["mech"])
        bot.combat = Combat(world, self.hello["config"])
        bot.cover = CoverPlanner(world, self.hello["config"])
        bot.motion = GroundSteering(world, self.hello["config"])
        # These real planners own their World too; no mixed-map certifications.
        bot.salvage.world = bot.opener.world = world
        return bot

    def test_current_shelter_owns_silence_even_with_known_charging_enemy(self):
        self.enemy["charging"] = True
        self.assertTrue(self.decide(sheltered=True))
        self.assertEqual(self.window.reason, "verified shelter")
        self.assertFalse(self.decide(sheltered=False))

    def test_damage_or_continuous_crossing_round_invalidates_repair(self):
        self.assertTrue(self.decide(sheltered=True))
        self.obs["projectiles"] = [dict(id=88, kind="gun", pos=[-70, 41.5, 7], vel=[0, -252, 0])]
        self.assertFalse(self.decide(sheltered=True))
        self.obs["projectiles"] = []
        self.obs["events"] = [dict(type="damaged", by=1, weapon="gun", amount=45)]
        self.assertFalse(self.decide(sheltered=True))

    def test_observed_regeneration_keeps_a_real_quiet_window(self):
        self.decide()
        self.obs.update(t=10.1, tick=202)
        self.me["hp"] += 4.5
        self.assertTrue(self.decide())
        self.assertEqual(self.window.reason, "observed regeneration")
        self.obs.update(t=10.2, tick=204)
        self.enemy["charging"] = True
        self.assertFalse(self.decide())

    def test_cube_health_or_long_observation_gap_is_not_regeneration_proof(self):
        self.decide()
        self.obs.update(t=10.1, tick=202)
        self.me.update(hp=756, max_hp=1456, cubes=1)
        self.assertFalse(self.decide())
        self.obs.update(t=12, tick=240)
        self.me["hp"] += 4.5
        self.assertFalse(self.decide())

    def test_recovery_route_and_full_laser_attack_coexist(self):
        bot = self.bot()
        self.me["weapons"][1] = dict(kind="laser", charge=0, cooldown=0,
                                    stats=copy.deepcopy(self.hello["config"]["weapons"]["laser"]))
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.me["weapons"][0])[0]
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "recover")
        self.assertTrue(action["fire"][1])
        self.assertLess(action["move"][0], 0)
        self.assertTrue(action["boost"])
        self.assertIsNone(bot.quiet_window.reason)

    def test_two_exposed_lanes_keep_escape_and_hostile_combat(self):
        bot = self.bot()
        second = dict(self.enemy, id=2, pos=[0, 45, 0], aim=[-2.57, 0])
        self.obs["mechs"].append(second)
        self.me["weapons"][1] = dict(kind="laser", charge=.75, cooldown=0,
                                    stats=copy.deepcopy(self.hello["config"]["weapons"]["laser"]))
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.me["weapons"][1])[0]
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "recover")
        self.assertIsNone(bot.duel)
        self.assertEqual(bot.combat.locked_id, 1)
        self.assertFalse(action["fire"][1])  # release the aligned full beam
        self.assertIsNone(bot.quiet_window.reason)
        self.assertLess(action["move"][0], 0)

    def test_a_real_wall_refuge_preserves_no_shots_while_repairing(self):
        bot = self.bot(flat_world([rectangle(-40, -40, -35, 40)]))
        self.me["weapons"][1] = dict(kind="mortar", cooldown=0,
                                    stats=copy.deepcopy(self.hello["config"]["weapons"]["mortar"]))
        action = bot.act(self.obs)
        self.assertTrue(bot.cover.sheltered)
        self.assertEqual(action["fire"], [False, False])
        self.assertEqual(bot.quiet_window.reason, "verified shelter")

    def test_demonstrated_repair_does_not_restart_a_movement_duel(self):
        bot = self.bot()
        # A new otherwise-admissible duel cannot discard a working repair.
        self.me["hp"] = 795
        self.enemy["hp"] = 820
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.me["weapons"][0])[0]
        bot.act(self.obs)
        self.obs.update(t=10.1, tick=202)
        self.me["hp"] = 799.5
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "recover")
        self.assertIsNone(bot.duel)
        self.assertEqual(action["fire"], [False, False])
        self.assertEqual(bot.quiet_window.reason, "observed regeneration")

    def test_ordinary_weak_finish_cannot_erase_demonstrated_repair(self):
        bot = self.bot()
        self.enemy["hp"] = 150
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.me["weapons"][0])[0]
        bot.act(self.obs)
        self.obs.update(t=10.1, tick=202)
        self.me["hp"] += 4.5
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "recover")
        self.assertIsNone(bot.duel)
        self.assertEqual(action["fire"], [False, False])

if __name__ == "__main__":
    unittest.main()
