"""Shot-window geometry and shared-torso guards, not authoritative match physics."""
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.geometry import angle_error


class FireWindowTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.combat = Combat(self.world, self.config)
        self.me = self.obs["self"]
        self.me.update(pos=[-90, 0, 0], vel=[0, 0, 0], aim=[0, 0], grounded=True)
        self.gun = self.weapon("gun", ammo=12, reload=0)
        self.me["weapons"] = [self.gun, None]
        self.enemy = {"id": 1, "kind": "mech", "pos": [10, 0, 0],
                      "vel": [0, 12, 0], "hp": 1400, "max_hp": 1400}

    def weapon(self, kind, **extra):
        return {"kind": kind, "cooldown": 0,
                "stats": copy.deepcopy(self.config["weapons"][kind]), **extra}

    def miss_at_launch(self, aim, launch_delay):
        """Independent constant-velocity closest-approach calculation in 3D."""
        origin = [self.me["pos"][i]+self.me["vel"][i]*launch_delay for i in range(3)]
        origin[2] += self.me["stats"]["muzzle_height"]
        target = [self.enemy["pos"][i]+self.enemy["vel"][i]*launch_delay for i in range(3)]
        target[2] += self.config["mech"]["height"]*.5
        speed = self.gun["stats"]["speed"]
        shot = [speed*math.cos(aim[1])*math.cos(aim[0]),
                speed*math.cos(aim[1])*math.sin(aim[0]), speed*math.sin(aim[1])]
        relative = [target[i]-origin[i] for i in range(3)]
        closing = [shot[i]-self.enemy["vel"][i] for i in range(3)]
        time = max(0, sum(relative[i]*closing[i] for i in range(3))/sum(v*v for v in closing))
        return math.sqrt(sum((relative[i]-closing[i]*time)**2 for i in range(3)))

    def test_gun_command_accounts_for_target_motion_and_own_muzzle_before_launch(self):
        self.me["vel"] = [0, -12, 0]
        old_aim = self.combat.solve(self.me, self.enemy, self.gun)[0]
        aim, _, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertLess(self.miss_at_launch(aim, .05), 1e-6)
        self.assertGreater(self.miss_at_launch(old_aim, .05), 1.1)
        self.me["aim"] = aim
        _, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[0])

    def test_primary_laser_turn_cannot_spend_gun_round_using_old_observed_lead(self):
        self.me["weapons"][1] = self.weapon("laser", charge=.35)
        gun_lead = self.combat.solve(self.me, self.enemy, self.gun)[0]
        self.me["aim"] = gun_lead
        aim, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertGreater(abs(angle_error(aim[0], gun_lead[0])), math.atan2(2.8, 100))
        self.assertFalse(fire[0])
        self.assertTrue(fire[1])

    def test_second_step_gun_cooldown_uses_a_later_interception_point(self):
        first, _, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.gun["cooldown"] = .08
        second, _, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertGreater(second[0], first[0]+.004)
        self.me["aim"] = second
        _, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[0])

    def test_large_unacquired_turn_does_not_fire_from_an_imaginary_aim(self):
        self.me["aim"] = [math.pi, 0]
        _, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertFalse(fire[0])

    def test_partial_and_full_laser_charge_wait_for_both_possible_release_aims(self):
        laser = self.weapon("laser", charge=self.config["weapons"]["laser"]["charge"])
        self.me["weapons"] = [None, laser]
        self.me["aim"] = [.06, 0]
        aim, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[1])
        self.me["aim"] = aim
        _, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertFalse(fire[1])
        laser["charge"] *= .5
        _, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[1])

    def test_laser_tracks_future_relative_motion_without_projectile_lead(self):
        self.me["vel"] = [0, -12, 0]
        self.me["weapons"] = [None, self.weapon("laser", charge=.2)]
        aim, _, _ = self.combat.action(self.me, [self.enemy], False, False)
        self.assertAlmostEqual(aim[0], math.atan2(1.2, 100), places=6)
        self.assertLess(aim[0], .02)

    def test_planned_boost_braking_is_used_instead_of_constant_old_velocity(self):
        self.me["vel"] = [0, -19.5, 0]
        drifting, _, _ = self.combat.action(self.me, [self.enemy], False, False)
        braking, _, _ = self.combat.action(self.me, [self.enemy], False, False,
                                          move=[0, 0], boost=False)
        self.assertLess(braking[0], drifting[0])
        self.assertGreater(drifting[0]-braking[0], 1e-5)

    def test_range_edge_keeps_an_earlier_valid_opportunity(self):
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0])
        self.enemy.update(pos=[229.06, 0, 0], vel=[1, 0, 0])
        old_solution = self.combat.solve(self.me, self.enemy, self.gun)
        self.assertIsNotNone(old_solution)
        self.me["aim"] = old_solution[0]
        aim, fire, target = self.combat.action(self.me, [self.enemy], False, False)
        self.assertIsNotNone(aim)
        self.assertEqual(target["id"], self.enemy["id"])
        self.assertTrue(fire[0])

    def test_future_muzzle_ray_does_not_shoot_into_a_corner_clear_only_at_observation(self):
        self.world = flat_world([rectangle(0, -20, 1, 20)])
        self.combat = Combat(self.world, self.config)
        self.me.update(pos=[-5, 20.1, 0], vel=[0, -19.5, 0])
        self.enemy.update(pos=[20, 21, 0], vel=[0, 0, 0])
        old_solution = self.combat.solve(self.me, self.enemy, self.gun)
        self.assertIsNotNone(old_solution)
        self.me["aim"] = old_solution[0]
        _, fire, target = self.combat.action(self.me, [self.enemy], False, False,
                                            move=[0, -1], boost=True)
        self.assertIsNone(target)
        self.assertFalse(fire[0])

    def test_two_kinematic_brackets_do_not_multiply_wall_ray_work(self):
        self.me["aim"] = self.combat.solve(self.me, self.enemy, self.gun)[0]
        with patch.object(self.world, "line_clear", wraps=self.world.line_clear) as rays:
            self.combat.action(self.me, [self.enemy], False, False)
        self.assertEqual(rays.call_count, 1)
        blocked_world = flat_world([rectangle(-30, -20, -25, 20)])
        blocked = Combat(blocked_world, self.config)
        with patch.object(blocked_world, "line_clear", wraps=blocked_world.line_clear) as rays:
            _, fire, target = blocked.action(self.me, [self.enemy], False, False)
        self.assertEqual(rays.call_count, 1)
        self.assertIsNone(target)
        self.assertFalse(fire[0])

    def test_stationary_target_and_instant_weapon_paths_remain_compatible(self):
        self.enemy["vel"] = [0, 0, 0]
        self.me["aim"] = self.combat.solve(self.me, self.enemy, self.gun)[0]
        aim, fire, _ = self.combat.action(self.me, [self.enemy], False, False,
                                         move=[0, 0], boost=False)
        self.assertEqual(aim, self.me["aim"])
        self.assertTrue(fire[0])
        for kind in ("mortar", "lightning"):
            with self.subTest(kind=kind):
                self.enemy["pos"] = [-60, 0, 0]
                weapon = self.weapon(kind)
                self.me["weapons"] = [None, weapon]
                solution = self.combat.solve(self.me, self.enemy, weapon)
                self.assertIsNotNone(solution)
                self.me["aim"] = solution[0]
                aim, fire, _ = self.combat.action(self.me, [self.enemy], False, False,
                                                 move=[0, 1], boost=True)
                self.assertEqual(aim, solution[0])
                self.assertTrue(fire[1])

    def test_fast_opposite_orbits_do_not_permanently_starve_gun_trigger(self):
        # A constant 100 m separation with two 19.5 m/s circular trajectories.
        # Actual torso motion is advanced independently at 20 Hz. Ammo is held
        # available to isolate acquisition/trigger gating, not weapon-clock DPS.
        self.me.update(pos=[-50, 0, 0], vel=[0, -19.5, 0])
        self.enemy.update(pos=[50, 0, 0], vel=[0, 19.5, 0])
        self.me["aim"] = self.combat.solve(self.me, self.enemy, self.gun)[0]
        triggers = 0
        for decision in range(100):
            angle = decision*.1*.39
            sine, cosine = math.sin(angle), math.cos(angle)
            self.me.update(pos=[-50*cosine, -50*sine, 0],
                           vel=[19.5*sine, -19.5*cosine, 0])
            self.enemy.update(pos=[50*cosine, 50*sine, 0],
                              vel=[-19.5*sine, 19.5*cosine, 0])
            aim, fire, _ = self.combat.action(self.me, [self.enemy], False, False)
            triggers += fire[0]
            for _ in range(2):
                yaw_limit = self.me["stats"]["turn_rate"]*.05
                pitch_limit = self.me["stats"]["pitch_rate"]*.05
                self.me["aim"] = [
                    self.me["aim"][0]+max(-yaw_limit, min(yaw_limit,
                        angle_error(aim[0], self.me["aim"][0]))),
                    self.me["aim"][1]+max(-pitch_limit, min(pitch_limit,
                        aim[1]-self.me["aim"][1]))]
        self.assertGreaterEqual(triggers, 90)


if __name__ == "__main__":
    unittest.main()
