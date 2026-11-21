"""Coherent movement ownership, real geometry, and unchanged weapon actions."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from arc_physics import move
from sentinel.arc_retreat import ArcRetreat
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.opener import Opener
from sentinel.salvage import KillSalvage
from sentinel.strategy import Bot


class NoRetreat:
    def choose(self, obs, move, boost, **kwargs):
        return move, boost


class ArcRetreatTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[-35, 0, 0], vel=[-11.7, 0, 0], aim=[0, -.045], hp=1400,
                       max_hp=1400, energy=100, grounded=True, in_zone=True, cubes=0)
        self.me["weapons"][0].update(ammo=12, cooldown=0, reload=0)
        self.me["weapons"][1] = dict(kind="laser", charge=0, cooldown=0,
                                    stats=copy.deepcopy(self.config["weapons"]["laser"]))
        self.enemy = dict(id=1, kind="mech", pos=[20, 0, 0], vel=[-11.7, 0, 0],
                         aim=[math.pi, 0], hp=1400, max_hp=1400, cubes=0,
                         weapons=["gun", "lightning"], charging=False)
        self.obs.update(t=10, tick=200, alive=16, mechs=[self.enemy], events=[],
                        projectiles=[], crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.controller = ArcRetreat(self.world, self.config)
        self.normal = [-.8, .6]

    def choose(self, **kwargs):
        return self.controller.choose(self.obs, self.normal, False, circle=([0, 0], 118),
                                      fire=[True, True], active_ids={1}, **kwargs)

    def bot(self, enabled):
        bot = Bot(self.hello)
        bot.world = self.world
        bot.nav = Navigator(self.world, self.config["mech"])
        bot.combat = Combat(self.world, self.config)
        bot.cover = CoverPlanner(self.world, self.config)
        bot.motion = GroundSteering(self.world, self.config)
        bot.opener = Opener(self.world, self.config)
        bot.salvage = KillSalvage(self.world, self.config)
        bot.arc_retreat = self.controller if enabled else NoRetreat()
        return bot

    def test_full_bot_changes_direction_without_changing_attacks_or_adding_boost(self):
        ordinary = self.bot(False).act(copy.deepcopy(self.obs))
        changed = self.bot(True).act(copy.deepcopy(self.obs))
        self.assertEqual(changed["move"], [-1, 0])
        self.assertNotEqual(changed["move"], ordinary["move"])
        for key in ("tick", "aim", "fire", "boost", "reload"):
            self.assertEqual(changed.get(key), ordinary.get(key))

    def test_short_lease_keeps_direction_while_ordinary_steering_reverses(self):
        selected, boost = self.choose()
        self.assertEqual(selected, [-1, 0])
        self.assertFalse(boost)
        self.me["weapons"][1]["charge"] = .1
        for _ in range(2):
            self.assertTrue(move(self.me, dict(move=selected, boost=False), self.world, True))
            self.enemy["pos"][0] -= 11.7*.05
        self.obs.update(t=10.1, tick=202)
        self.normal = [-.5, -math.sqrt(.75)]
        self.assertEqual(self.choose(), (selected, False))

    def test_next_charge_risk_does_not_surrender_an_already_safe_retreat_path(self):
        self.choose()
        self.controller.phase = "cooldown"
        self.enemy["pos"][0] = self.me["pos"][0]+49
        self.obs.update(t=12.4, tick=248)
        self.normal = [0, 1]
        self.assertEqual(self.choose(), ([-1, 0], False))

    def test_initially_too_close_far_or_non_arc_cases_are_strictly_inert(self):
        for case in ("close", "far", "gun", "stopped"):
            with self.subTest(case=case):
                self.setUp()
                if case == "close": self.enemy["pos"][0] = self.me["pos"][0]+48
                if case == "far": self.enemy["pos"][0] = self.me["pos"][0]+70
                if case == "gun": self.enemy["weapons"] = ["gun"]
                if case == "stopped": self.enemy["vel"] = [0, 0, 0]
                self.assertEqual(self.choose(), (self.normal, False))

    def test_live_wall_body_growth_zone_and_roof_support_abort(self):
        self.world = flat_world([rectangle(-51, -20, -50, 20)])
        self.controller = ArcRetreat(self.world, self.config)
        self.assertEqual(self.choose()[0], [-1, 0])
        self.me["stats"]["radius"] = 5
        self.obs.update(t=10.1, tick=202)
        self.assertEqual(self.choose(), (self.normal, False))
        self.setUp()
        self.me["pos"][2] = 20
        self.assertEqual(self.choose(), (self.normal, False))
        self.setUp()
        output = self.controller.choose(self.obs, self.normal, False, circle=([0, 0], 42),
                                        fire=[True, True], active_ids={1})
        self.assertEqual(output, (self.normal, False))

    def test_growing_opponent_cannot_fit_through_our_body_margin(self):
        self.enemy["cubes"] = 400
        self.assertEqual(self.choose(), (self.normal, False))

    def test_added_continuous_projectile_contact_hands_back_the_ordinary_dodge(self):
        self.obs["projectiles"] = [dict(id=88, kind="gun", pos=[-5, -2.65, 7], vel=[-252, 0, 0])]
        self.assertEqual(self.choose(), (self.normal, False))
        self.assertIn("projectile", self.controller.reason)

    def test_second_exposed_lane_or_real_unseen_attacker_cancels(self):
        self.choose()
        self.obs["events"] = [dict(type="damaged", by=2, weapon="gun", amount=45)]
        self.assertEqual(self.choose(), (self.normal, False))
        self.obs.update(t=10.2, tick=204, events=[])
        self.assertEqual(self.choose(), (self.normal, False))
        self.setUp()
        self.obs["mechs"].append(dict(self.enemy, id=2, pos=[-90, 20, 0], weapons=["gun"]))
        self.assertEqual(self.choose(), (self.normal, False))

    def test_higher_priority_controller_and_existing_escape_boost_keep_their_controls(self):
        self.choose()
        self.assertEqual(self.choose(reserved=True), (self.normal, False))
        self.setUp()
        output = self.controller.choose(self.obs, self.normal, True, circle=([0, 0], 118),
                                        fire=[True, True], active_ids={1})
        self.assertEqual(output, (self.normal, True))

    def test_mortar_forecast_uses_the_configured_splash_radius(self):
        self.config["weapons"]["mortar"]["splash_radius"] = 10
        self.obs["projectiles"] = [dict(id=77, kind="mortar", pos=[-35, 12, 0], vel=[0, 0, 0])]
        stationary = [[-35, 0, 0] for _ in range(7)]
        self.assertIn(77, self.controller._contacts(self.obs, stationary))


if __name__ == "__main__":
    unittest.main()
