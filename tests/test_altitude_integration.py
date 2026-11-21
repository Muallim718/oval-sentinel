"""Full-bot altitude priorities on an actual solid-roof fixture.

Flight feedback is tested separately; these cases exercise controller ownership,
eligibility, equipment/trigger safety, geometry, and escape priority.
"""
from contextlib import contextmanager
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.cover import firing_lane
from sentinel.strategy import Bot


class AltitudeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.roof = rectangle(0, -30, 45, 30, top=18)
        self.world = flat_world([self.roof])
        self.me = self.obs["self"]
        self.me.update(pos=[-6, 0, 0], vel=[0, 0, 0], hp=1400, energy=100,
                       grounded=True, in_zone=True, aim=[0, 0])
        self.obs.update(t=0, tick=0, alive=16, mechs=[], events=[], projectiles=[],
                        crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.me["weapons"][0].update(ammo=12, reload=0, cooldown=0)

    def bot(self):
        # All actual Bot components initialize against the same geometric
        # fixture. No flight, cover, navigation, or combat behavior is mocked.
        with patch("sentinel.strategy.World", return_value=self.world):
            bot = Bot(self.hello)
        self.assertGreater(len(bot.altitude.sites), 0)
        return bot

    def enemy(self, position=(-80, 0, 0)):
        return {"id": 1, "kind": "mech", "pos": list(position),
                "vel": [0, 0, 0], "aim": [0, 0], "hp": 1400,
                "max_hp": 1400, "weapons": ["gun", "laser"]}

    def advance(self, time):
        self.obs.update(t=time, tick=round(time*20), events=[])

    def held_roof(self, bot, side="left"):
        candidates = [site for site in bot.altitude.sites
                      if (site["launch"][0] < 0 if side == "left"
                          else site["launch"][0] > 45)]
        self.assertTrue(candidates)
        site = min(candidates, key=lambda item: abs(item["launch"][1]))
        bot.altitude.site, bot.altitude.phase = site, "hold"
        bot.altitude.deadline = math.inf
        self.me.update(pos=list(site["hold"]), vel=[0, 0, 0], grounded=True,
                       hp=self.me["max_hp"], energy=self.me["max_energy"])
        self.advance(10)
        return site

    @contextmanager
    def forbid_ground_controller(self, bot):
        with patch.object(bot.nav, "waypoint", side_effect=AssertionError("ground nav owns flight")), \
             patch.object(bot.motion, "choose", side_effect=AssertionError("ground steering owns flight")), \
             patch.object(bot.cover, "choose", side_effect=AssertionError("ground cover owns flight")):
            yield

    def test_healthy_early_bot_starts_valid_roof_before_pressure(self):
        bot = self.bot()
        action = bot.act(self.obs)
        self.assertIsNotNone(bot.altitude.site)
        self.assertIn(bot.altitude.phase, ("approach", "ascend"))
        self.assertEqual(action["tick"], self.obs["tick"])
        self.assertEqual(action["fire"], [False, False])
        self.assertTrue(action["jump"])

    def test_low_health_low_energy_or_charged_laser_does_not_start_flight(self):
        for condition in ("health", "energy", "charge"):
            with self.subTest(condition=condition):
                self.me.update(hp=1400, energy=100)
                self.me["weapons"][1] = None
                if condition == "health":
                    self.me["hp"] = 700
                elif condition == "energy":
                    self.me["energy"] = 50
                else:
                    self.me["weapons"][1] = {
                        "kind": "laser", "charge": .3, "cooldown": 0,
                        "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
                bot = self.bot()
                action = bot.act(self.obs)
                self.assertIsNone(bot.altitude.site)
                self.assertFalse(action["jump"])

    def test_near_hunter_or_fresh_damage_vetoes_preemptive_launch(self):
        for condition in ("hunter", "damage"):
            with self.subTest(condition=condition):
                self.obs.update(mechs=[], events=[])
                self.me["hp"] = 1400
                if condition == "hunter":
                    self.obs["mechs"] = [self.enemy()]
                else:
                    self.me["hp"] = 1355
                    self.obs["events"] = [{"type": "damaged", "weapon": "gun",
                                            "amount": 45, "by": 1, "bearing": 0}]
                bot = self.bot()
                action = bot.act(self.obs)
                self.assertIsNone(bot.altitude.site)
                self.assertFalse(action["jump"])

    def test_exposed_laser_at_200_meters_is_pressure_even_outside_near_hunter_gate(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        target = self.enemy((-206, 0, 0))
        target["charging"] = True
        self.obs["mechs"] = [target]
        self.assertEqual(math.dist(self.me["pos"], target["pos"]), 200)
        self.assertTrue(self.world.line_clear([-206, 0, 7], [-6, 0, 8.55]))
        bot = self.bot()
        action = bot.act(self.obs)
        self.assertIsNone(bot.altitude.site)
        self.assertFalse(action["jump"])

    def test_new_pressure_aborts_ground_approach_instead_of_late_takeoff(self):
        self.me["pos"] = [-35, 0, 0]
        bot = self.bot()
        bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "approach")
        self.advance(.1)
        self.me["hp"] = 1355
        self.obs["mechs"] = [self.enemy((-60, 0, 0))]
        self.obs["events"] = [{"type": "damaged", "weapon": "gun",
                                "amount": 45, "by": 1, "bearing": math.pi}]
        action = bot.act(self.obs)
        self.assertIsNone(bot.altitude.site)
        self.assertFalse(action["jump"])

    def test_direct_ascent_owns_controls_despite_stale_ground_cover_and_jet(self):
        bot = self.bot()
        bot.act(self.obs)
        site = bot.altitude.site
        self.assertEqual(bot.altitude.phase, "ascend")
        self.me.update(pos=[*site["launch"][:2], 8], vel=[0, 0, 5], grounded=False,
                       energy=85)
        self.advance(.5)
        bot.cover_active, bot.jet_until = True, 100
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "ascend")
        self.assertTrue(action["boost"])
        self.assertFalse(action["jump"])
        self.assertEqual(action["fire"], [False, False])
        self.assertLess(bot.jet_until, self.obs["t"])

    def test_healthy_roof_hold_persists_without_ground_navigation(self):
        bot = self.bot()
        site = self.held_roof(bot)
        with self.forbid_ground_controller(bot):
            for now in (10, 30, 60):
                self.advance(now)
                action = bot.act(self.obs)
                self.assertEqual(bot.altitude.phase, "hold")
                self.assertIs(bot.altitude.site, site)
                self.assertEqual(action["move"], [0, 0])
                self.assertFalse(action["boost"])
                self.assertFalse(action["jump"])

    def test_roof_recovery_does_not_start_gun_or_laser_fire(self):
        bot = self.bot()
        self.held_roof(bot)
        self.me["hp"] = 700
        self.me["weapons"][1] = {
            "kind": "laser", "charge": 0, "cooldown": 0,
            "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.obs["mechs"] = [self.enemy((-100, 0, 0))]
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
        self.assertEqual(action["fire"], [False, False])
        self.assertEqual(bot.altitude.phase, "hold")

    def test_healthy_hold_can_fire_an_actual_clear_aligned_gun_solution(self):
        bot = self.bot()
        self.held_roof(bot)
        target = self.enemy((-100, 0, 0))
        self.obs["mechs"] = [target]
        solution = bot.combat.solve(self.me, target, self.me["weapons"][0])
        self.assertIsNotNone(solution)
        self.me["aim"] = solution[0]
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "hold")
        self.assertTrue(action["fire"][0])
        self.assertEqual(action["move"], [0, 0])

    def test_non_hold_flight_phases_suppress_otherwise_aligned_shots(self):
        for phase in ("ascend", "cross", "land", "settle", "exit"):
            with self.subTest(phase=phase):
                self.obs.update(mechs=[], events=[])
                bot = self.bot()
                site = self.held_roof(bot)
                bot.altitude.phase, bot.altitude.deadline = phase, self.obs["t"]+10
                bot.altitude.cross_started = self.obs["t"]
                bot.altitude.last_rise = self.obs["t"]
                bot.altitude.best_height = 8
                if phase == "ascend":
                    self.me.update(pos=[*site["launch"][:2], 8], vel=[0, 0, 5], grounded=False)
                elif phase == "cross":
                    self.me.update(pos=[*site["launch"][:2], 20], vel=[0, 0, 4], grounded=False)
                elif phase == "land":
                    self.me.update(pos=[*site["landing"][:2], 20], vel=[0, 0, -2], grounded=False)
                elif phase == "settle":
                    self.me.update(pos=list(site["landing"]), vel=[0, 0, 0], grounded=True)
                else:
                    bot.altitude.begin_exit(self.obs, ([0, 0], 118), "fixture exit")
                target = self.enemy((-100, self.me["pos"][1], 0))
                self.obs["mechs"] = [target]
                solution = bot.combat.solve(self.me, target, self.me["weapons"][0])
                self.assertIsNotNone(solution, "scenario must offer a real gun shot")
                self.me["aim"] = solution[0]
                with self.forbid_ground_controller(bot):
                    action = bot.act(self.obs)
                self.assertEqual(action["fire"], [False, False])

    def test_own_roof_blocks_close_below_shots_and_actual_muzzle_solves_far_target(self):
        bot = self.bot()
        site = self.held_roof(bot)
        self.me["pos"] = list(site["landing"])
        target = self.enemy((-3, self.me["pos"][1], 0))
        gun = self.me["weapons"][0]
        laser = {"kind": "laser", "charge": 0, "cooldown": 0,
                 "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.assertIsNone(bot.combat.solve(self.me, target, gun))
        self.assertIsNone(bot.combat.solve(self.me, target, laser))
        self.obs["mechs"] = [target]
        action = bot.act(self.obs)
        self.assertGreaterEqual(action["aim"][1], self.me["stats"]["min_pitch"])
        self.assertLessEqual(action["aim"][1], self.me["stats"]["max_pitch"])
        target["pos"][0] = -100
        solution = bot.combat.solve(self.me, target, gun)
        self.assertIsNotNone(solution)
        vertical = self.hello["config"]["mech"]["height"]*.5-(
            self.me["pos"][2]+self.me["stats"]["muzzle_height"])
        horizontal = abs(self.me["pos"][0]-target["pos"][0])
        self.assertAlmostEqual(solution[0][1], math.atan2(vertical, horizontal), places=6)

    def test_flight_keeps_gun_and_handles_upgrade_offer(self):
        self.me["weapons"][1] = {
            "kind": "mortar", "cooldown": 0,
            "stats": copy.deepcopy(self.hello["config"]["weapons"]["mortar"])}
        self.obs["offer"] = {"choices": [{"id": "gun_rate"}, {"id": "servos"},
                                          {"id": "nanites"}]}
        bot = self.bot()
        action = bot.act(self.obs)
        self.assertIsNotNone(bot.altitude.site)
        self.assertEqual(action["pick"], 1)
        self.assertNotEqual(action.get("drop"), 0)
        self.assertNotIn("take", action)
        self.assertEqual(action["fire"], [False, False])

    def test_zone_exit_chooses_toward_circle_even_if_no_exit_is_already_inside(self):
        bot = self.bot()
        self.held_roof(bot, "right")
        self.obs["zone"].update(center=[-80, 0], radius=25,
                                next_center=[-80, 0], next_radius=25)
        self.me["in_zone"] = False
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertLess(action["move"][0], 0)
        self.assertFalse(action["boost"])
        self.assertFalse(action["jump"])

    def test_stalled_grounded_roof_exit_keeps_control_until_terrain_landing(self):
        bot = self.bot()
        self.held_roof(bot, "right")
        self.obs["zone"].update(center=[-80, 0], radius=25,
                                next_center=[-80, 0], next_radius=25)
        self.me["in_zone"] = False
        # Freeze physical observations on the roof to exercise a genuinely
        # stalled exit. "grounded" here means roof support, not terrain support.
        with self.forbid_ground_controller(bot):
            for decision in range(41):
                self.advance(10+decision*.1)
                action = bot.act(self.obs)
                self.assertIsNotNone(bot.altitude.site)
                self.assertEqual(bot.altitude.phase, "exit")
                self.assertEqual(action["fire"], [False, False])
                self.assertFalse(action["jump"])
        landing = bot.altitude.exit_goal
        self.assertIsNotNone(landing)
        self.me.update(pos=list(landing), vel=[0, 0, 0], grounded=True)
        self.advance(14.2)
        bot.act(self.obs)
        self.assertIsNone(bot.altitude.site)
        self.assertIsNone(bot.altitude.phase)

    def test_ground_weapon_hit_ends_roof_hold_and_exit_owns_airborne_descent(self):
        bot = self.bot()
        site = self.held_roof(bot)
        target = self.enemy((-100, 0, 0))
        self.assertLess(target["pos"][2], site["landing"][2]-5)
        self.assertTrue(firing_lane(self.world, self.hello["config"], self.me["pos"],
                                    self.me, target)[0])
        self.obs["mechs"] = [target]
        self.me["hp"] = 1085  # One full 315-damage beam from the initial 1400 HP.
        self.obs["events"] = [{"type": "damaged", "weapon": "laser", "amount": 315,
                                "by": 1, "bearing": math.pi}]
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
            self.assertEqual(bot.altitude.phase, "exit")
            self.assertEqual(action["fire"], [False, False])
            self.assertGreater(math.hypot(*action["move"]), .1)
            landing = bot.altitude.exit_goal
            self.me.update(pos=[*landing[:2], 9], vel=[0, 0, -3], grounded=False)
            self.advance(10.2)
            action = bot.act(self.obs)
            self.assertEqual(bot.altitude.phase, "exit")
            self.assertIsNotNone(bot.altitude.site)
            self.assertEqual(action["fire"], [False, False])
        self.me.update(pos=list(landing), vel=[0, 0, 0], grounded=True)
        self.advance(10.3)
        bot.act(self.obs)
        self.assertIsNone(bot.altitude.site)

    def test_exposed_ground_laser_charge_at_200_meters_ends_roof_hold_before_hit(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        bot = self.bot()
        site = self.held_roof(bot)
        target = self.enemy((self.me["pos"][0]-200, self.me["pos"][1], 0))
        target.update(charging=True, aim=[0, .1])
        self.assertEqual(math.dist(self.me["pos"][:2], target["pos"][:2]), 200)
        self.assertLess(200, self.hello["config"]["weapons"]["laser"]["range"])
        self.assertLess(target["pos"][2], site["landing"][2]-5)
        self.assertTrue(firing_lane(self.world, self.hello["config"], self.me["pos"],
                                    self.me, target)[0])
        self.obs["mechs"] = [target]
        with self.forbid_ground_controller(bot):
            action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "exit")
        self.assertEqual(action["fire"], [False, False])
        self.assertGreater(math.hypot(*action["move"]), .1)

    def test_roof_hold_does_not_reload_partial_magazine_while_engaging_far_target(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        bot = self.bot()
        self.held_roof(bot)
        target = self.enemy((self.me["pos"][0]-190, self.me["pos"][1], 0))
        self.obs["mechs"] = [target]
        gun = self.me["weapons"][0]
        gun.update(ammo=5, reload=0, cooldown=0)
        solution = bot.combat.solve(self.me, target, gun)
        self.assertIsNotNone(solution)
        self.me["aim"] = solution[0]
        self.assertGreater(math.dist(self.me["pos"][:2], target["pos"][:2]), 150)
        action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "hold")
        self.assertTrue(action["fire"][0])
        self.assertFalse(action["reload"])

    def test_ground_roof_approach_still_takes_reachable_laser_without_dropping_gun(self):
        self.me["pos"] = [-35, 0, 0]
        pickup = {"id": 8001, "kind": "laser", "pos": [-35, 1.5, 3.5]}
        self.obs["pickups"] = [pickup]
        self.assertLessEqual(math.dist(self.me["pos"][:2], pickup["pos"][:2]), 3.5)
        self.assertLessEqual(abs(self.me["pos"][2]-pickup["pos"][2]), 4)
        self.assertIsNone(self.me["weapons"][1])
        bot = self.bot()
        action = bot.act(self.obs)
        self.assertEqual(bot.altitude.phase, "approach")
        self.assertEqual(action["take"], pickup["id"])
        self.assertNotEqual(action.get("drop"), 0)
        self.assertEqual(action["fire"], [False, False])


if __name__ == "__main__":
    unittest.main()
