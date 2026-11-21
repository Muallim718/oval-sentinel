"""Short reload opportunities retain combat; they do not introduce readiness AI."""
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.reload_arm import ReloadArm
from sentinel.strategy import Bot
from sentinel.opener import Opener
from sentinel.navigation import Navigator
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.salvage import KillSalvage


class ReloadArmTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], aim=[0, 0], hp=1000,
                       max_hp=1400, energy=100, grounded=True, in_zone=True)
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=0, reload=2.4, cooldown=0)
        self.enemy = {"id": 1, "kind": "mech", "pos": [80, 0, 0], "vel": [-8, 0, 0],
                      "aim": [math.pi, 0], "hp": 1000, "max_hp": 1400, "weapons": ["gun"]}
        self.pickup = {"id": 8001, "kind": "laser", "pos": [0, 10, 0]}
        self.obs.update(t=20, tick=400, alive=16, events=[], projectiles=[], mechs=[self.enemy],
                        pickups=[self.pickup], crates=[], cubes=[])
        self.circle = ([0, 0], 118)
        self.arm = ReloadArm(self.world, self.config)

    def choose(self, enemies=None, recovering=False):
        return self.arm.choose(self.obs, [(e, 1) for e in (enemies or [self.enemy])],
                               self.circle, recovering=recovering)

    def advance(self, seconds=.1):
        self.obs["t"] += seconds
        self.obs["tick"] += round(seconds*20)
        self.obs["events"] = []

    def sheltered(self):
        self.world = flat_world([rectangle(-2, -60, 2, 60)])
        self.me.update(pos=[-8, 18, 0], hp=700)
        self.pickup["pos"] = [-8, 35, 0]
        self.gun.update(ammo=12, reload=0)
        self.arm = ReloadArm(self.world, self.config)

    def test_reload_admits_real_ten_meter_weapon_that_both_baseline_gates_exclude(self):
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertFalse(mission.protected)
        self.assertAlmostEqual(mission.eta, .65)
        self.assertAlmostEqual(mission.ready_at-self.obs["t"], .65+1.65)
        self.assertFalse(mission.sprint)
        self.assertIsNone(mission.take)
        opener = Opener(self.world, self.config)
        self.assertIsNone(opener.choose(self.obs, [(self.enemy, 1)], self.circle))
        bot = Bot(self.hello)
        bot.world, bot.nav = self.world, Navigator(self.world, self.config["mech"])
        bot.select_mode(self.obs)
        _, kind, _ = bot.choose_goal(self.obs, False, [(self.enemy, 1)])
        self.assertNotEqual(kind, "weapon")

    def test_exposed_pickup_does_not_create_a_general_gun_only_readiness_posture(self):
        self.gun.update(ammo=8, reload=0)
        self.assertIsNone(self.choose())
        self.assertIsNone(self.arm.current)

    def test_new_exposed_detour_must_fit_the_actual_remaining_own_reload(self):
        self.gun["reload"] = .2
        self.assertIsNone(self.choose())
        self.gun.update(ammo=0, reload=0)  # The ordinary reload can start now.
        self.advance()
        self.assertIsNotNone(self.choose())

    def loaded_duel(self):
        self.obs.update(t=100, tick=2000)
        self.me["hp"] = self.me["max_hp"]
        self.gun.update(ammo=12, reload=0)
        self.enemy["pos"] = [55, 0, 0]
        self.pickup["kind"] = "lightning"

    def test_loaded_gun_can_take_a_bounded_sideways_duel_detour(self):
        self.loaded_duel()
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertAlmostEqual(mission.eta, .65)
        self.assertLessEqual(self.arm.current["until"]-self.obs["t"], 1.6)
        self.assertIn("while firing", self.arm.reason)
        self.me["hp"] = 850
        self.advance()
        self.assertIsNone(self.choose())

    def test_loaded_guard_rejects_late_pressure_or_routing_toward_the_hunter(self):
        for changed in ("late", "health", "ahead", "armed"):
            with self.subTest(changed=changed):
                self.setUp()
                self.loaded_duel()
                if changed == "late":
                    self.obs.update(t=151, tick=3020)
                elif changed == "health":
                    self.me["hp"] = 1000
                elif changed == "ahead":
                    self.pickup["pos"] = [10, 0, 0]
                else:
                    self.enemy["weapons"] = ["gun", "laser"]
                self.assertIsNone(self.choose())

    def test_covered_short_route_can_collect_while_recovering_without_reload(self):
        self.sheltered()
        mission = self.choose(recovering=True)
        self.assertIsNotNone(mission)
        self.assertTrue(mission.protected)
        self.assertLessEqual(mission.eta, 3)

    def test_two_actual_attack_lanes_or_charging_laser_abort(self):
        other = {**self.enemy, "id": 2, "pos": [0, -80, 0], "vel": [0, 8, 0]}
        self.obs["mechs"].append(other)
        self.assertIsNone(self.choose([self.enemy, other]))
        self.setUp()
        self.enemy.update(charging=True, weapons=["gun", "laser"])
        self.assertIsNone(self.choose())

    def test_severe_health_storm_or_final_duel_keeps_baseline_priority(self):
        for change in (lambda: self.me.update(hp=400),
                       lambda: self.me.update(in_zone=False),
                       lambda: self.obs.update(alive=2)):
            with self.subTest(change=change):
                self.setUp()
                change()
                self.assertIsNone(self.choose())

    def test_weapon_cannot_be_on_a_roof_or_behind_a_blocked_straight_corridor(self):
        self.pickup["pos"][2] = 12
        self.assertIsNone(self.choose())
        self.setUp()
        self.world = flat_world([rectangle(-6, 4, 6, 6)])
        self.arm = ReloadArm(self.world, self.config)
        self.assertIsNone(self.choose())

    def test_three_second_limit_is_physical_not_only_a_distance_label(self):
        self.sheltered()
        self.pickup["pos"] = [-8, -25, 0]  #43m exceeds three-second walk.
        self.assertIsNone(self.choose(recovering=True))
        self.setUp()
        self.circle = ([-70, 0], 50)
        self.assertIsNone(self.choose())

    def test_take_requires_actual_range_and_brakes_instead_of_overshooting(self):
        self.me["pos"] = [0, 7, 0]
        mission = self.choose()
        self.assertEqual(mission.take, 8001)
        self.assertEqual(mission.move, (0., 0.))

    def test_actual_receipt_ends_route_and_initial_equip_is_not_every_shot_cooldown(self):
        self.assertIsNotNone(self.choose())
        self.advance(.7)
        self.me["weapons"][1] = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                                   "stats": copy.deepcopy(self.config["weapons"]["laser"])}
        self.obs["events"] = [{"type": "took", "id": 8001, "kind": "laser", "slot": 1}]
        self.assertIsNone(self.choose())
        self.assertIsNone(self.arm.current)
        self.assertEqual(self.arm.state, "equipping")
        self.advance(1.65)
        self.me["weapons"][1]["cooldown"] = 0
        self.assertIsNone(self.choose())
        self.assertEqual(self.arm.state, "armed")
        self.advance()
        self.me["weapons"][1]["cooldown"] = 1.65
        self.assertIsNone(self.choose())
        self.assertEqual(self.arm.state, "armed")

    def test_gone_pickup_and_expired_or_stalled_commitment_are_not_blind_chases(self):
        self.assertIsNotNone(self.choose())
        self.advance()
        self.obs["events"] = [{"type": "take_failed", "id": 8001, "reason": "gone"}]
        self.obs["pickups"] = []
        self.assertIsNone(self.choose())
        self.setUp()
        self.choose()
        self.advance(1.1)
        self.assertIsNone(self.choose())
        self.assertIn("progress", self.arm.reason)
        self.setUp()
        self.choose()
        self.advance(3.1)
        self.assertIsNone(self.choose())
        self.assertIn("expired", self.arm.reason)

    def test_equip_delay_and_in_flight_bullet_are_counted_after_arrival(self):
        self.pickup["pos"] = [0, 0, 0]
        self.me["hp"] = 560
        self.assertIsNotNone(self.choose())
        self.advance()
        self.obs["projectiles"] = [{"id": 201, "kind": "gun", "pos": [120, 0, 7],
                                     "vel": [-252, 0, 0]}]
        # The bullet reaches us ~0.46s after zero-time arrival, while equipping.
        self.assertIsNone(self.choose())

    def test_changing_health_or_enemy_lane_rechecks_the_live_commitment(self):
        self.assertIsNotNone(self.choose())
        self.advance()
        self.me["hp"] = 500
        self.assertIsNone(self.choose())
        self.setUp()
        self.choose()
        self.advance()
        self.enemy["pos"] = [30, 0, 0]
        self.assertIsNone(self.choose())

    def test_no_actions_modify_combat_and_late_empty_inventory_is_not_a_global_mission(self):
        mission = self.choose()
        self.assertFalse(hasattr(mission, "aim"))
        self.assertFalse(hasattr(mission, "fire"))
        self.setUp()
        self.obs.update(t=100, tick=2000)
        self.assertIsNone(self.choose())


class ReloadArmIntegrationTests(unittest.TestCase):
    setUp = ReloadArmTests.setUp

    def bot(self):
        bot = Bot(self.hello)
        bot.world, bot.nav = self.world, Navigator(self.world, self.config["mech"])
        bot.combat, bot.cover = Combat(self.world, self.config), CoverPlanner(self.world, self.config)
        bot.motion = GroundSteering(self.world, self.config)
        bot.salvage, bot.opener = KillSalvage(self.world, self.config), Opener(self.world, self.config)
        bot.reload_arm = self.arm
        return bot

    def test_pickup_owns_legs_but_retains_brawler_target_aim_and_gun_fire(self):
        bot = self.bot()
        action = bot.act(self.obs)
        self.assertTrue(bot.arm_active)
        self.assertEqual(bot.commitment.target_id, 1)
        self.assertEqual(bot.duel["id"], 1)
        self.assertEqual(bot.mode, "fight")
        self.assertAlmostEqual(bot.fight_range, 42)
        self.assertLess(abs(action["aim"][0]), .1)
        self.obs.update(t=20.1, tick=402)
        self.me["pos"] = [0, 7, 0]
        self.gun.update(ammo=5, reload=0)
        self.me["aim"] = bot.combat.solve(self.me, self.enemy, self.gun)[0]
        action = bot.act(self.obs)
        self.assertTrue(action["fire"][0])
        self.assertEqual(action["take"], 8001)
        self.assertNotIn("drop", action)
        self.obs.update(t=20.2, tick=404)
        self.me["weapons"][1] = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                                   "stats": copy.deepcopy(self.config["weapons"]["laser"])}
        bot.act(self.obs)
        self.assertFalse(bot.arm_active)
        self.assertNotEqual(bot.goal_kind, "reload weapon")
        self.assertEqual(bot.commitment.target_id, 1)

    def test_verified_kill_reward_has_priority_over_optional_arming(self):
        bot = self.bot()
        with patch.object(bot.salvage, "choose", return_value=(0, -20)), patch.object(
                bot.reload_arm, "choose", side_effect=AssertionError("arming stole salvage")):
            bot.act(self.obs)
        self.assertEqual(bot.mode, "salvage")
        self.assertFalse(bot.arm_active)


if __name__ == "__main__":
    unittest.main()
