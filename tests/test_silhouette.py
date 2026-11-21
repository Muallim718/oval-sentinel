"""Physical silhouette shots, including the actual torso ray through cover."""
import copy
import math
import time
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat, ExposedSolution, aim_at


class SilhouetteTests(unittest.TestCase):
    def setUp(self):
        self.hello, obs = fixture()
        self.config = self.hello["config"]
        self.me = copy.deepcopy(obs["self"])
        self.me.update(pos=[-40, 0, 0], vel=[0, 0, 0], aim=[0, 0])
        self.gun = {"kind": "gun", "stats": self.config["weapons"]["gun"],
                    "ammo": 12, "reload": 0, "cooldown": 0}
        self.laser = {"kind": "laser", "stats": self.config["weapons"]["laser"],
                      "charge": .75, "cooldown": 0}
        self.me["weapons"] = [self.gun, None]
        self.enemy = {"id": 10, "kind": "mech", "pos": [40, 0, 0],
                      "vel": [0, 0, 0], "hp": 1400, "max_hp": 1400,
                      "cubes": 0, "weapons": ["gun"]}

    def physical_hit(self, world, aim, kind="gun"):
        """Independent 20Hz straight projectile/beam through a known x-plane.

        The target is stationary here, so its front cylinder cap has x=37.5
        only at y=0. Step the shot, interpolate its actual cylinder crossing,
        and reject an earlier map collision. No production targeting helper.
        """
        direction = [math.cos(aim[1])*math.cos(aim[0]),
                     math.cos(aim[1])*math.sin(aim[0]), math.sin(aim[1])]
        start = [-40, 0, self.me["stats"]["muzzle_height"]]
        speed = self.config["weapons"]["gun"]["speed"] if kind == "gun" else 10000
        previous = [start[i]+direction[i]*(self.me["stats"]["radius"]+.5) for i in range(3)]
        if not world.line_clear(start, previous):
            return False
        for _ in range(30):
            current = [previous[i]+direction[i]*speed*.05 for i in range(3)]
            # Segment / horizontal cylinder quadratic, then a vertical check.
            vx, vy = current[0]-previous[0], current[1]-previous[1]
            dx, dy = previous[0]-40, previous[1]
            a, b, c = vx*vx+vy*vy, 2*(dx*vx+dy*vy), dx*dx+dy*dy-2.5**2
            disc = b*b-4*a*c
            if disc >= 0:
                for fraction in sorted(((-b-math.sqrt(disc))/(2*a), (-b+math.sqrt(disc))/(2*a))):
                    if 0 <= fraction <= 1:
                        hit = [previous[i]+(current[i]-previous[i])*fraction for i in range(3)]
                        if 0 <= hit[2] <= 9:
                            return world.line_clear(previous, hit)
            if not world.line_clear(previous, current):
                return False
            previous = current
        return False

    def test_upper_body_gun_shot_really_hits_when_center_is_blocked(self):
        world = flat_world([rectangle(10, -15, 20, 15, top=7.3)])
        combat = Combat(world, self.config)
        origin = [-40, 0, self.me["stats"]["muzzle_height"]]
        self.assertFalse(world.line_clear(origin, [40, 0, 4.5]))
        self.assertFalse(self.physical_hit(world, aim_at(origin, [40, 0, 4.5])))
        aim, fire, target = combat.action(self.me, [self.enemy], False, False)
        self.assertEqual(target["id"], 10)
        self.assertFalse(fire[0])  # current horizontal aim hits the wall
        self.me["aim"] = aim
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[0])
        self.assertTrue(self.physical_hit(world, aim))

    def test_flank_shot_waits_even_when_old_broad_aim_box_contains_blocked_ray(self):
        world = flat_world([rectangle(10, -15, 20, .3, top=20)])
        combat = Combat(world, self.config)
        solved = combat.solve(self.me, self.enemy, self.gun)
        self.assertIsInstance(solved, ExposedSolution)
        self.assertGreater(solved[1][1], 1)
        self.me["aim"] = aim_at([-40, 0, 7], [40, 0, 4.5])
        self.assertLess(abs(solved[0][0]-self.me["aim"][0]), math.atan2(2.8, 80))
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertFalse(fire[0])
        self.me["aim"] = solved[0]
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[0])
        self.assertTrue(self.physical_hit(world, solved[0]))

    def test_moving_flank_cannot_certify_a_static_future_body_graze(self):
        world = flat_world([rectangle(10, -30, 20, 4)])
        combat = Combat(world, self.config)
        self.enemy["vel"] = [0, 19.5, 0]
        solved = combat.solve(self.me, self.enemy, self.gun)
        self.assertIsInstance(solved, ExposedSolution)
        unsafe = [solved[0][0]+.0059, solved[0][1]]
        # Independently intersect the actual moving cylinder. The 3m forward
        # barrel causes this outer ray to pass ahead before the body arrives.
        direction = [math.cos(unsafe[1])*math.cos(unsafe[0]),
                     math.cos(unsafe[1])*math.sin(unsafe[0]), math.sin(unsafe[1])]
        start = [-40+3*direction[0], 3*direction[1], 7+3*direction[2]]
        rx, ry = start[0]-40, start[1]
        vx, vy = direction[0]*252, direction[1]*252-19.5
        a, b, c = vx*vx+vy*vy, 2*(rx*vx+ry*vy), rx*rx+ry*ry-2.5**2
        self.assertLess(b*b-4*a*c, 0)
        self.me["aim"] = unsafe
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertFalse(fire[0])
        self.me["aim"] = solved[0]
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[0])

    def test_laser_holds_behind_blocked_boresight_then_releases_real_head_hit(self):
        world = flat_world([rectangle(10, -15, 20, 15, top=7.3)])
        combat = Combat(world, self.config)
        self.me["weapons"] = [None, self.laser]
        aim, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertTrue(fire[1])
        self.me["aim"] = aim
        _, fire, _ = combat.action(self.me, [self.enemy], False, False)
        self.assertFalse(fire[1])
        self.assertTrue(self.physical_hit(world, aim, "laser"))

    def test_full_wall_rejects_all_samples_and_does_not_fire(self):
        combat = Combat(flat_world([rectangle(10, -15, 20, 15, top=20)]), self.config)
        self.assertIsNone(combat.solve(self.me, self.enemy, self.gun))
        self.assertIsNone(combat.solve(self.me, self.enemy, self.laser))
        self.assertEqual(combat.action(self.me, [self.enemy], False, False),
                         (None, [False, False], None))

    def test_open_center_solution_is_exact_original_intercept(self):
        world = flat_world()
        combat = Combat(world, self.config)
        self.enemy["vel"] = [0, 12, 0]
        solved = combat.solve(self.me, self.enemy, self.gun)
        self.assertNotIsInstance(solved, ExposedSolution)
        from sentinel.combat import intercept
        flight = intercept([-40, 0, 7], [40, 0, 4.5], [0, 12, 0], 252)
        point = [40, 12*flight, 4.5]
        self.assertEqual(solved, (aim_at([-40, 0, 7], point), point, 2.5, 9))

    def test_fallback_stays_in_live_enlarged_body(self):
        world = flat_world([rectangle(10, -15, 20, 15, top=8)])
        combat = Combat(world, self.config)
        self.enemy["cubes"] = 5
        solved = combat.solve(self.me, self.enemy, self.gun)
        self.assertIsInstance(solved, ExposedSolution)
        point, radius, height = solved[1:]
        self.assertEqual((radius, height), (3.125, 11.25))
        self.assertLess(math.hypot(point[0]-solved.center[0], point[1]-solved.center[1]), radius)
        self.assertLess(point[2], self.enemy["pos"][2]+height)

    def test_fallback_range_and_live_pitch_are_not_clamped_into_invalid_shots(self):
        world = flat_world([rectangle(10, -15, 20, 15, top=7.3)])
        combat = Combat(world, self.config)
        self.me["stats"]["max_pitch"] = 0
        self.assertIsNone(combat.solve(self.me, self.enemy, self.gun))
        self.me["stats"]["max_pitch"] = 1.3
        self.gun = copy.deepcopy(self.gun)
        self.gun["stats"]["range"] = 79
        self.assertIsNone(combat.solve(self.me, self.enemy, self.gun))

    def test_fallback_expired_budget_fails_closed(self):
        world = flat_world([rectangle(10, -15, 20, 15, top=7.3)])
        combat = Combat(world, self.config)
        with patch("sentinel.combat.time.perf_counter", side_effect=[0, 1]):
            self.assertIsNone(combat.solve(self.me, self.enemy, self.gun))
        solved = combat.solve(self.me, self.enemy, self.gun)
        self.me["aim"] = solved[0]
        self.assertFalse(combat._exposed_boresight(self.me, self.gun, solved,
                                                 self.me["aim"], time.perf_counter()-1))

    def test_other_weapon_solvers_do_not_gain_silhouette_behavior(self):
        combat = Combat(flat_world([rectangle(-20, -15, -10, 15, top=20)]), self.config)
        lightning = {"kind": "lightning", "stats": self.config["weapons"]["lightning"]}
        self.enemy["pos"][0] = 0
        self.assertIsNone(combat.solve(self.me, self.enemy, lightning))


if __name__ == "__main__":
    unittest.main()
