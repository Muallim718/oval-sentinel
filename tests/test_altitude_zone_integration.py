"""Phase-aware roof-zone priorities through the full bot, without flight physics."""
from contextlib import contextmanager
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.cover import firing_lane
from sentinel.strategy import Bot


class AltitudeZoneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.roof = rectangle(-25, -30, 25, 30, top=25)
        self.world = flat_world([self.roof])
        self.me = self.obs["self"]
        self.me.update(pos=[-31, 0, 0], vel=[0, 0, 0], hp=1400, energy=100,
                       grounded=True, in_zone=True, aim=[0, 0])
        self.obs.update(t=10, tick=200, alive=16, events=[], mechs=[], projectiles=[],
                        crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.me["weapons"][0].update(ammo=12, reload=0, cooldown=0)

    def bot(self):
        with patch("sentinel.strategy.World", return_value=self.world):
            bot = Bot(self.hello)
        self.assertTrue(bot.altitude.sites)
        return bot

    def stage(self, bot, phase="hold"):
        sites = [site for site in bot.altitude.sites if site["launch"][0] < -25]
        site = min(sites, key=lambda item: abs(item["launch"][1]))
        bot.altitude.site, bot.altitude.phase = site, phase
        bot.altitude.hold_goal = tuple(site["hold"])
        bot.altitude.deadline = math.inf
        self.me.update(pos=list(site["hold"]), vel=[0, 0, 0], grounded=True)
        return site

    def future_circle(self, center, radius):
        # The current circle still contains the roof; this is the smaller circle
        # reached within the bot's rotation horizon, not an invented teleport.
        self.obs["zone"].update(next_center=list(center), next_radius=radius,
                                shrink_start=self.obs["t"], shrink_end=self.obs["t"]+8)
        return list(center), radius

    @contextmanager
    def forbid_ground(self, bot):
        with patch.object(bot.nav, "waypoint", side_effect=AssertionError("ground nav took roof")), \
             patch.object(bot.motion, "choose", side_effect=AssertionError("ground steering took roof")), \
             patch.object(bot.cover, "choose", side_effect=AssertionError("ground shelter took roof")):
            yield

    def test_preflight_still_requires_launch_and_landing_inside_small_future_circle(self):
        for radius in (25, 5):
            with self.subTest(radius=radius):
                self.me.update(pos=[-31, 0, 0], grounded=True, vel=[0, 0, 0])
                self.future_circle([0, 0], radius)
                bot = self.bot()
                self.assertTrue(all(math.hypot(*site["hold"][:2]) < radius
                                    for site in bot.altitude.sites))
                action = bot.act(self.obs)
                self.assertIsNone(bot.altitude.site)
                self.assertFalse(action["jump"])

    def test_ground_approach_does_not_ignore_its_still_required_launch(self):
        bot = self.bot()
        site = self.stage(bot, "approach")
        self.me.update(pos=list(site["launch"]), grounded=True)
        self.future_circle([0, 0], 25)
        bot.act(self.obs)
        self.assertIsNone(bot.altitude.site)

    def test_ascent_and_crossing_ignore_abandoned_launch_but_keep_safe_entry(self):
        for phase in ("ascend", "cross"):
            with self.subTest(phase=phase):
                bot = self.bot()
                site = self.stage(bot, phase)
                self.future_circle([0, 0], 25)
                self.assertGreater(math.hypot(*site["launch"][:2]), 25)
                self.assertLess(math.hypot(*site["landing"][:2]), 20)
                self.me.update(pos=[*site["launch"][:2], 10 if phase == "ascend" else 27],
                               vel=[0, 0, 3], grounded=False)
                bot.altitude.best_height = self.me["pos"][2]
                bot.altitude.last_rise = bot.altitude.cross_started = self.obs["t"]
                with self.forbid_ground(bot):
                    action = bot.act(self.obs)
                self.assertEqual(bot.altitude.phase, phase)
                self.assertEqual(action["fire"], [False, False])
                if phase == "ascend":
                    self.assertTrue(action["boost"])
                else:
                    self.assertGreater(action["move"][0], .5)

    def test_landed_hold_remains_owned_when_only_abandoned_launch_is_outside(self):
        bot = self.bot()
        site = self.stage(bot)
        self.future_circle([0, 0], 25)
        self.assertGreater(math.hypot(*site["launch"][:2]), 25)
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "hold")
        self.assertIs(bot.altitude.site, site)
        self.assertEqual(action["move"], [0, 0])
        self.assertFalse(action["jump"])
        self.assertFalse(action["boost"])

    def test_five_meter_retarget_updates_live_goal_and_debug_without_mutating_cached_sites(self):
        bot = self.bot()
        site = self.stage(bot)
        bot.debug = True
        cached_geometry = [{key: value for key, value in item.items() if key != "prism"}
                           for item in bot.altitude.sites]
        self.future_circle([10, 0], 5)
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        goal = bot.altitude.hold_goal
        self.assertEqual(bot.altitude.phase, "settle")
        self.assertLess(math.dist(goal[:2], [10, 0]), 4)
        self.assertTrue(bot.altitude.supported(self.roof, goal, self.me["stats"]["radius"]+.3))
        self.assertTrue(self.world.body_clear(*goal, self.me["stats"]["radius"]+.3,
                                              self.me["stats"]["height"], 0))
        self.assertEqual(bot.goal, tuple(goal[:2]))
        self.assertEqual(action["debug"]["points"][0]["at"], list(goal))
        self.assertGreater(action["move"][0], .1)
        self.assertEqual(cached_geometry,
            [{key: value for key, value in item.items() if key != "prism"}
             for item in bot.altitude.sites])
        self.assertEqual(site["hold"], (0, 0, 25))

    def test_grounded_land_and_settle_can_retarget_even_when_old_entry_is_outside(self):
        for phase in ("land", "settle"):
            with self.subTest(phase=phase):
                bot = self.bot()
                site = self.stage(bot, phase)
                self.me.update(pos=list(site["landing"]), grounded=True, vel=[0, 0, 0])
                self.future_circle([10, 0], 5)
                self.assertGreater(math.dist(site["landing"][:2], [10, 0]), 5)
                with self.forbid_ground(bot):
                    action = bot.act(self.obs)
                self.assertEqual(bot.altitude.phase, "settle")
                self.assertLess(math.dist(bot.altitude.hold_goal[:2], [10, 0]), 4)
                self.assertGreater(action["move"][0], .1)
                self.assertFalse(action["jump"])
                self.assertFalse(action["boost"])

    def test_live_growth_can_invalidate_old_launch_while_held_roof_remains_clear(self):
        bot = self.bot()
        site = self.stage(bot)
        self.future_circle([0, 0], 25)
        scale = 2.4
        self.me["cubes"] = 28
        for key in ("radius", "height", "eye_height", "muzzle_height"):
            self.me["stats"][key] = self.hello["config"]["mech"][key]*scale
        self.me["hp"] = self.me["max_hp"] = 1960
        self.assertFalse(bot.altitude.valid_site(site, self.me))
        self.assertTrue(self.world.body_clear(*self.me["pos"], self.me["stats"]["radius"]+.3,
                                              self.me["stats"]["height"], 0))
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "hold")
        self.assertIs(bot.altitude.site, site)
        self.assertEqual(action["move"], [0, 0])

    def test_weapon_hit_wins_over_simultaneous_zone_retarget(self):
        bot = self.bot()
        self.stage(bot)
        self.future_circle([10, 0], 5)
        self.me["hp"] = 1085
        self.obs["events"] = [{"type": "damaged", "weapon": "laser", "amount": 315,
                                "by": 1, "bearing": math.pi}]
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertEqual(action["fire"], [False, False])

    def test_charging_laser_wins_over_simultaneous_zone_retarget(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        bot = self.bot()
        self.stage(bot)
        self.future_circle([10, 0], 5)
        enemy = {"id": 1, "kind": "mech", "pos": [-200, 0, 0], "vel": [0, 0, 0],
                 "aim": [0, .1], "hp": 1400, "max_hp": 1400,
                 "weapons": ["gun", "laser"], "charging": True}
        self.assertTrue(firing_lane(self.world, self.hello["config"], self.me["pos"], self.me, enemy)[0])
        self.obs["mechs"] = [enemy]
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertEqual(action["fire"], [False, False])

    def test_lost_ground_support_wins_over_simultaneous_zone_retarget(self):
        bot = self.bot()
        self.stage(bot)
        self.future_circle([10, 0], 5)
        self.me.update(pos=[0, 0, 26], vel=[0, 0, 1], grounded=False)
        with self.forbid_ground(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertFalse(action["jump"])

    def test_pressure_on_tick_after_retarget_still_interrupts_landed_settle(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        for pressure in ("hit", "charge"):
            with self.subTest(pressure=pressure):
                self.obs.update(events=[], mechs=[])
                self.me["hp"] = 1400
                bot = self.bot()
                self.stage(bot)
                self.future_circle([10, 0], 5)
                with self.forbid_ground(bot):
                    bot.act(self.obs)
                self.assertEqual(bot.altitude.phase, "settle")
                self.obs.update(t=10.1, tick=202)
                if pressure == "hit":
                    self.me["hp"] = 1085
                    self.obs["events"] = [{"type": "damaged", "weapon": "laser",
                                            "amount": 315, "by": 1, "bearing": math.pi}]
                else:
                    self.obs["mechs"] = [{"id": 1, "kind": "mech", "pos": [-200, 0, 0],
                        "vel": [0, 0, 0], "aim": [0, .1], "hp": 1400, "max_hp": 1400,
                        "weapons": ["gun", "laser"], "charging": True}]
                with self.forbid_ground(bot):
                    action = bot.act(self.obs)
                self.assertEqual(bot.altitude.phase, "exit")
                self.assertEqual(action["fire"], [False, False])

    def test_no_roof_overlap_uses_bounded_retarget_then_owned_exit(self):
        bot = self.bot()
        self.stage(bot)
        self.future_circle([80, 0], 5)
        with patch.object(bot.altitude, "roof_goal_valid", wraps=bot.altitude.roof_goal_valid) as examined:
            with self.forbid_ground(bot):
                action = bot.act(self.obs)
        self.assertLessEqual(examined.call_count, 10)  # Existing-goal probe plus nine anchors.
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertGreater(bot.altitude.exit_goal[0], 0)
        self.assertGreater(action["move"][0], .1)


if __name__ == "__main__":
    unittest.main()
