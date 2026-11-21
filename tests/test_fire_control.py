"""Gun opportunities and shared aim across decision-sized weapon windows."""
import copy
import math
import unittest

from sentinel.combat import Combat, target_center
from sentinel.fire_control import FireControl, intercept_with_barrel
from test_bot import fixture, flat_world, rectangle


class FireControlTests(unittest.TestCase):
    def setUp(self):
        hello, obs = fixture()
        self.config = hello["config"]
        self.me = obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], aim=[0, 0], energy=100)
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, cooldown=0, reload=0)
        self.control = FireControl(flat_world(), self.config)
        self.enemy = {"id": 2, "kind": "mech", "pos": [72, 0, 0], "vel": [0, 0, 0],
                      "aim": [math.pi, 0], "hp": 900, "max_hp": 1400, "weapons": ["gun"]}

    def equip(self, kind, **state):
        self.me["weapons"][1] = {
            "kind": kind, "stats": copy.deepcopy(self.config["weapons"][kind]),
            "cooldown": 0, **state,
        }

    def decide(self, *, retreat=False, boost=False, return_fire=False):
        return self.control.action(self.me, [self.enemy], retreat, False,
                                   boost=boost, return_fire=return_fire)

    def align(self):
        center, radius, height = target_center(self.enemy, self.config)
        self.me["aim"] = self.control.direct_aim(self.me, center, radius, height,
                                                self.enemy["vel"], self.gun, .05)

    def test_barrel_intercept_meets_translating_body_at_launch_distance(self):
        origin, point, velocity = (0, 0, 7), (91, 0, 4.5), (-3, 19, 0)
        flight = intercept_with_barrel(origin, point, velocity, 252, 3)
        meeting_point = [p + v * flight for p, v in zip(point, velocity)]
        self.assertAlmostEqual(math.dist(origin, meeting_point), 3 + 252 * flight)

    def test_gun_fires_as_torso_slews_into_reachable_lane(self):
        self.me["aim"] = [-.14, 0.]
        legacy = Combat(self.control.world, self.config)
        self.assertFalse(legacy.action(self.me, [self.enemy], False, False)[1][0])
        self.assertTrue(self.decide()[1][0])
        self.me["aim"] = [-.29, 0.]
        self.assertFalse(self.decide()[1][0])
        self.gun["cooldown"] = .08
        self.assertTrue(self.decide()[1][0])
        self.gun["cooldown"] = .12
        self.assertFalse(self.decide()[1][0])

    def test_unready_laser_does_not_interrupt_ready_gun(self):
        self.enemy["vel"] = [0, 18, 0]
        self.equip("laser", cooldown=.25, charge=0)
        self.align()
        self.assertEqual(self.decide()[1], [True, False])

    def test_armed_laser_can_finish_target_before_full_charge(self):
        self.align()
        self.enemy["hp"] = 85
        self.equip("laser", charge=.2)
        aim, fire, target = self.decide()
        self.assertEqual(fire, [True, False])
        self.assertEqual(target["id"], self.enemy["id"])
        self.assertAlmostEqual(aim[0], 0)

    def test_full_health_enemy_keeps_charge_in_stable_fight(self):
        self.align()
        self.equip("laser", charge=.2)
        self.assertEqual(self.decide()[1], [True, True])
        self.me["weapons"][1]["charge"] = self.config["weapons"]["laser"]["charge"]
        self.assertEqual(self.decide()[1], [True, False])

    def test_gun_and_arc_can_fire_after_damage_during_escape(self):
        self.enemy["pos"] = [31, 0, 0]
        self.align()
        self.equip("lightning")
        self.assertEqual(self.decide(retreat=True, boost=True, return_fire=True)[1], [True, True])
        self.assertEqual(self.decide(retreat=True)[1], [False, False])
        self.equip("laser", charge=0)
        self.assertEqual(self.decide(retreat=True, return_fire=True)[1], [True, False])

    def test_body_above_low_wall_is_hittable_but_full_cover_is_not(self):
        self.enemy["pos"] = [45, 0, 0]
        partial = rectangle(40, -4, 44, 4, top=6.5)
        self.control = FireControl(flat_world([partial]), self.config)
        self.align()
        self.assertTrue(self.decide()[1][0])
        self.control = FireControl(flat_world([rectangle(40, -4, 44, 4)]), self.config)
        self.assertFalse(self.decide()[1][0])
