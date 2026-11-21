"""Full-bot readiness and protected-loot priorities; not a match simulator."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.provisioning import Provisioner
from sentinel.strategy import Bot


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-8, 18, 0], vel=[0, 0, 0], hp=1400, grounded=True,
                       energy=100, aim=[0, 0], in_zone=True)
        self.obs.update(t=0, tick=0, alive=16, mechs=[], events=[], projectiles=[],
                        crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.world = flat_world([rectangle(-2, -40, 2, 40)])
        self.enemy = {"id": 1, "kind": "mech", "pos": [35, 0, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                      "max_hp": 1400, "weapons": ["gun", "laser"]}
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, reload=0, cooldown=0)

    def bot(self):
        bot = Bot(self.hello)
        bot.world = self.world
        bot.nav = Navigator(self.world, self.hello["config"]["mech"])
        bot.combat = Combat(self.world, self.hello["config"])
        bot.cover = CoverPlanner(self.world, self.hello["config"])
        bot.motion = GroundSteering(self.world, self.hello["config"])
        bot.provision = Provisioner(self.world, self.hello["config"])
        self.obs["mechs"] = [self.enemy]
        return bot

    def open_duel(self):
        self.world = flat_world()
        self.me["pos"] = [-70, 0, 0]
        self.enemy["pos"] = [0, 0, 0]
        bot = self.bot()
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.gun)[0]
        return bot

    def cube(self):
        self.obs["cubes"] = [{"id": 5001, "pos": [-8, 28, 0]}]

    def advance(self, time):
        self.obs.update(t=time, tick=round(time*20), events=[])

    def selected_weapon_mission(self):
        self.world = flat_world()
        self.me["pos"] = [-70, 0, 0]
        self.enemy["pos"] = [50, 0, 0]
        self.obs["zone"].update(radius=180, next_radius=180)
        bot = self.bot()
        self.obs["mechs"] = []
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [-70, 110, 0]}]
        bot.act(self.obs)  # Select the actual mission before the hunter appears.
        self.assertEqual(bot.goal_kind, "weapon")
        self.assertEqual(bot.goal, (-70, 110))
        self.advance(.1)
        self.obs["mechs"] = [self.enemy]
        self.obs["pickups"] = []  # Remembering the selected item is deliberate.
        return bot

    def test_gun_only_readiness_avoids_closing_but_keeps_defensive_fire(self):
        bot = self.open_duel()
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "evade")
        self.assertIsNone(bot.duel)
        self.assertTrue(action["fire"][0])
        self.assertLess(action["move"][0], .05)
        self.assertNotEqual(bot.goal_kind, "fight")

    def test_existing_weapon_mission_continues_without_65_meter_duel_attraction(self):
        bot = self.selected_weapon_mission()
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "arm")
        self.assertIsNone(bot.duel)
        self.assertEqual(bot.goal_kind, "weapon")
        self.assertEqual(bot.goal, (-70, 110))
        self.assertFalse(bot.cover_active)
        self.assertFalse(bot.provision_active)  # 110 m is not a certified corridor.
        self.assertGreater(action["move"][1], .5)

    def test_crossfire_puts_protection_ahead_of_existing_weapon_mission(self):
        bot = self.selected_weapon_mission()
        self.obs["mechs"].append({**self.enemy, "id": 2, "pos": [45, 20, 0]})
        bot.act(self.obs)
        self.assertEqual(bot.mode, "evade")
        self.assertIsNone(bot.duel)

    def test_recent_hit_puts_protection_ahead_of_existing_weapon_mission(self):
        bot = self.selected_weapon_mission()
        self.me["hp"] = 1355
        self.obs["events"] = [{"type": "damaged", "weapon": "gun", "amount": 45,
                                "by": 1, "bearing": 0}]
        bot.act(self.obs)
        self.assertEqual(bot.mode, "evade")
        self.assertIsNone(bot.duel)

    def test_initial_equip_gate_ends_at_first_ready_and_not_every_later_shot(self):
        bot = self.open_duel()
        bot.act(self.obs)  # Actual initial slot is empty, with no loot objective.
        laser = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                 "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.me["weapons"][1] = laser
        self.advance(.1)
        bot.act(self.obs)
        self.assertEqual(bot.provision.state, "equipping")
        self.assertEqual(bot.mode, "evade")
        self.assertIsNone(bot.duel)
        laser["cooldown"] = 0
        self.advance(1.8)
        bot.act(self.obs)
        self.assertNotEqual(bot.provision.state, "equipping")
        self.assertEqual(bot.mode, "fight")
        laser["cooldown"] = 1.2  # Ordinary cooldown after an actual shot.
        self.advance(1.9)
        bot.act(self.obs)
        self.assertNotEqual(bot.provision.state, "equipping")
        self.assertEqual(bot.mode, "fight")

    def test_weak_close_finish_overrides_gun_only_readiness(self):
        bot = self.open_duel()
        self.enemy.update(pos=[-50, 0, 0], hp=100)
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.gun)[0]
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "fight")
        self.assertEqual(bot.duel["id"], self.enemy["id"])
        self.assertTrue(action["fire"][0])

    def test_last_opponent_overrides_gun_only_readiness(self):
        bot = self.open_duel()
        self.obs["alive"] = 2
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "fight")
        self.assertEqual(bot.duel["id"], self.enemy["id"])
        self.assertTrue(action["fire"][0])

    def test_recovering_last_duel_does_not_start_special_resource_detour(self):
        bot = self.bot()
        self.me["hp"] = 700
        self.obs["alive"] = 2
        self.cube()
        bot.act(self.obs)
        self.assertTrue(bot.recovering)
        self.assertIsNone(bot.duel)  # This must not depend on a selected fight.
        self.assertFalse(bot.provision_active)
        self.assertNotEqual(bot.goal, (-8, 28))

    def test_outside_zone_start_prioritizes_entry_over_special_resource_plan(self):
        self.world = flat_world()
        self.me.update(pos=[-40, 0, 0], in_zone=False)
        self.obs["zone"].update(radius=30, next_radius=30)
        bot = self.bot()
        self.obs["mechs"] = []
        self.obs["cubes"] = [{"id": 5001, "pos": [-10, 0, 0]}]
        action = bot.act(self.obs)
        self.assertFalse(bot.provision_active)
        self.assertGreater(action["move"][0], .5)
        self.assertTrue(action["boost"])
        self.assertLess(math.dist(bot.goal, [0, 0]), 30)

    def test_imminent_zone_shrink_vetoes_otherwise_free_resource_permission(self):
        self.world = flat_world()
        self.me.update(pos=[-40, 0, 0], in_zone=True)
        self.obs["zone"].update(radius=118, next_radius=30,
                                shrink_start=0, shrink_end=10)
        bot = self.bot()
        self.obs["mechs"] = []
        self.obs["cubes"] = [{"id": 5001, "pos": [-10, 0, 0]}]
        action = bot.act(self.obs)
        self.assertFalse(bot.provision_active)
        self.assertGreater(action["move"][0], .5)
        self.assertLess(math.dist(bot.goal, [0, 0]), 30)

    def test_free_cube_collection_while_healing_does_not_attack_crate_or_npc(self):
        bot = self.bot()
        self.me["hp"] = 700
        self.cube()
        self.obs["crates"] = [{"id": 1001, "pos": [-8, 25, 0], "hp": 300}]
        self.obs["mechs"].append({"id": 101, "kind": "npc", "pos": [-110, 18, 0],
                                   "vel": [0, 0, 0], "hp": 350, "max_hp": 350})
        action = bot.act(self.obs)
        self.assertTrue(bot.provision_active)
        self.assertEqual(bot.goal_kind, "cube")
        self.assertEqual(bot.mode, "recover")
        self.assertEqual(action["fire"], [False, False])
        self.assertGreater(action["move"][1], .5)

    def test_visible_npc_chase_lane_vetoes_free_resource_override(self):
        bot = self.bot()
        self.me["hp"] = 700
        self.cube()
        self.obs["mechs"].append({"id": 101, "kind": "npc", "pos": [-8, 24, 0],
                                   "vel": [0, 0, 0], "hp": 350, "max_hp": 350})
        bot.act(self.obs)
        self.assertFalse(bot.provision_active)

    def test_fast_bullet_crossing_between_quarter_second_samples_vetoes_plan(self):
        bot = self.bot()
        self.me["hp"] = 700
        self.cube()
        # It crosses the entire 10 m corridor at .125-.165 s; neither t=0
        # nor t=.25 is near the corridor. Test an actual published gun speed.
        self.obs["projectiles"] = [{"id": 2001, "kind": "gun",
                                     "pos": [-8, 59.5, 7], "vel": [0, -252, 0]}]
        bot.act(self.obs)
        self.assertFalse(bot.provision_active)


if __name__ == "__main__":
    unittest.main()
