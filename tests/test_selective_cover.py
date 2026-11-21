"""Falsifiable partial-cover geometry; no full-match claims."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.cover import firing_lane
from sentinel.duel_commitment import DuelCommitment
from sentinel.geometry import distance
from sentinel.selective_cover import SelectiveCover


class SelectiveCoverTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world([rectangle(-3, -45, 3, 45)])
        self.me = self.obs["self"]
        self.me.update(pos=[-12, -51, 0], vel=[0, 0, 0], aim=[math.pi, 0],
                       hp=800, max_hp=1400, energy=100, grounded=True, in_zone=True)
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, reload=0, cooldown=0)
        self.strong = {"id": 1, "kind": "mech", "pos": [70, -20, 0], "vel": [0, 0, 0],
                       "aim": [math.pi, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}
        self.weak = {"id": 2, "kind": "mech", "pos": [-55, -51, 0], "vel": [0, 0, 0],
                     "aim": [0, 0], "hp": 140, "max_hp": 1400, "weapons": ["gun"]}
        self.obs.update(t=30, tick=600, alive=16, events=[], projectiles=[], mechs=[self.strong, self.weak])
        self.circle = ([0, 0], 118)
        self.control = SelectiveCover(self.world, self.config)

    def choose(self, recovering=True, quiet_shelter=False):
        return self.control.choose(self.obs, [(e, 1) for e in self.obs["mechs"]], self.circle,
                                   recovering=recovering, quiet_shelter=quiet_shelter)

    def arrive(self):
        plan = self.choose()
        self.assertIsNotNone(plan)
        self.me.update(pos=list(plan.goal), vel=[0, 0, 0])
        self.obs.update(t=30.6, tick=612)
        plan = self.choose()
        self.assertTrue(self.control.screened_once)
        return plan

    def test_body_safe_wall_anchor_screens_strong_but_preserves_weak_shot(self):
        self.assertTrue(firing_lane(self.world, self.config, self.me["pos"], self.me, self.strong)[0])
        self.assertTrue(firing_lane(self.world, self.config, self.me["pos"], self.me, self.weak)[0])
        plan = self.choose()
        self.assertIsNotNone(plan)
        self.assertEqual(plan.target["id"], 2)
        self.assertFalse(firing_lane(self.world, self.config, plan.goal, self.me, self.strong)[0])
        self.assertIsNotNone(Combat(self.world, self.config).solve(dict(self.me, pos=plan.goal), self.weak, self.gun))
        self.assertLessEqual(distance(self.me["pos"], plan.goal), 18)
        self.assertLessEqual(plan.transition_eta, .65)
        self.assertGreaterEqual(self.me["hp"]-plan.risk, 350)
        self.assertLessEqual(self.control.anchors, 12)

    def test_baseline_mechanics_decline_recovering_multi_lane_finish_before_damage(self):
        threats = [(e, 1) for e in self.obs["mechs"]]
        self.assertIsNone(DuelCommitment(self.config).choose(self.obs, threats, self.circle, self.world))
        combat = Combat(self.world, self.config)
        aim, fire, _ = combat.action(self.me, [self.weak], True, False, return_fire=False)
        self.assertIsNone(aim)
        self.assertFalse(any(fire))
        self.assertIsNotNone(self.choose())
        aim, fire, _ = combat.action(self.me, [self.weak], False, False)
        self.assertTrue(fire[0])
        self.assertFalse(self.obs["events"])  # No artificial damage unlock.

    def test_healthy_or_existing_quiet_recovery_shelter_is_not_interrupted(self):
        self.assertIsNone(self.choose(recovering=False))
        self.assertIsNone(self.choose(quiet_shelter=True))

    def test_real_weakness_requires_observed_health_live_ammo_and_no_reload(self):
        for change in (lambda: self.weak.update(hp=500), lambda: self.gun.update(ammo=4),
                       lambda: self.gun.update(reload=1.5), lambda: self.weak.pop("hp")):
            with self.subTest(change=change):
                self.setUp()
                change()
                self.assertIsNone(self.choose())

    def test_live_weak_target_disappearance_or_loss_of_shot_aborts(self):
        self.arrive()
        self.obs["mechs"] = [self.strong]
        self.assertIsNone(self.choose())
        self.setUp()
        self.arrive()
        self.weak["pos"] = [65, 0, 0]
        self.assertIsNone(self.choose())

    def test_flank_or_new_third_lane_aborts_immediately(self):
        self.arrive()
        self.strong["pos"] = [-35, -20, 0]
        self.assertIsNone(self.choose())
        self.assertIn("flank", self.control.reason)
        self.setUp()
        self.choose()
        third = dict(self.strong, id=3, pos=[-60, -20, 0])
        self.obs["mechs"].append(third)
        self.obs.update(t=30.1, tick=602)
        self.assertIsNone(self.choose())
        self.assertIn("new observed", self.control.reason)

    def test_actual_hit_overrides_geometrically_blocked_lane(self):
        self.arrive()
        self.obs["events"] = [{"type": "damaged", "by": 1, "weapon": "gun", "amount": 45}]
        self.assertIsNone(self.choose())
        self.assertIn("actual", self.control.reason)

    def test_hold_brakes_safely_and_absolute_crossing_deadline_cannot_extend(self):
        plan = self.arrive()
        self.assertTrue(plan.holding)
        self.assertEqual(plan.move, (0., 0.))
        self.setUp()
        self.choose()
        self.obs.update(t=30.9, tick=618)
        self.assertIsNone(self.choose())
        self.assertIn("in time", self.control.reason)

    def test_low_health_or_extra_laser_risk_cannot_spend_the_escape_reserve(self):
        self.me["hp"] = 700
        self.assertIsNone(self.choose())
        self.setUp()
        self.strong["weapons"].append("laser")
        self.assertIsNone(self.choose())
        self.me["hp"] = 1100
        self.assertIsNotNone(self.choose())

    def test_current_charging_lane_and_mortar_are_outside_the_admitted_model(self):
        self.strong.update(weapons=["gun", "laser"], charging=True)
        self.me["hp"] = 1400
        self.assertIsNone(self.choose())
        self.setUp()
        self.strong["weapons"].append("mortar")
        self.assertIsNone(self.choose())
        self.setUp()
        self.obs["projectiles"] = [{"kind": "mortar", "pos": [0, -20, 20]}]
        self.assertIsNone(self.choose())

    def test_zone_growth_and_airborne_state_cannot_keep_a_stale_screen(self):
        for change in (lambda: self.me.update(grounded=False),
                       lambda: self.me["stats"].update(radius=5),
                       lambda: setattr(self, "circle", ([70, 0], 40))):
            with self.subTest(change=change):
                self.setUp()
                self.choose()
                change()
                self.obs.update(t=30.1, tick=602)
                self.assertIsNone(self.choose())

    def test_expiry_or_actual_kill_hands_back_without_keeping_the_focus(self):
        self.arrive()
        self.obs.update(t=34, tick=680)
        self.assertIsNone(self.choose())
        self.assertIsNone(self.control.target_id)
        self.setUp()
        self.choose()
        self.obs["events"] = [{"type": "kill", "target": 2}]
        self.obs.update(t=30.1, tick=602)
        self.assertIsNone(self.choose())

    def test_real_twenty_hz_side_step_establishes_screen_and_brakes_without_teleport(self):
        action, screened_at = None, None
        for tick in range(40):
            now = 30+tick*.05
            self.obs.update(t=now, tick=600+tick)
            if tick % 2 == 0:
                action = self.choose()
                self.assertIsNotNone(action)
            stats = self.me["stats"]
            wanted = [action.move[i]*stats["walk_speed"] for i in range(2)]
            dv = [wanted[i]-self.me["vel"][i] for i in range(2)]
            f = min(1, stats["ground_accel"]*.05/max(1e-9, math.hypot(*dv)))
            self.me["vel"] = [self.me["vel"][i]+dv[i]*f for i in range(2)]+[0]
            p = [self.me["pos"][i]+self.me["vel"][i]*.05 for i in range(2)]+[0]
            self.assertTrue(self.world.walk_clear(self.me["pos"], p, stats["radius"]+.35,
                                                  stats["height"], stats["step_up"]))
            self.me["pos"] = p
            if not firing_lane(self.world, self.config, p, self.me, self.strong)[0] and screened_at is None:
                screened_at = now+.05-30
        self.assertIsNotNone(screened_at)
        self.assertLessEqual(screened_at, .65)
        self.assertTrue(self.control.plan.holding)
        self.assertFalse(firing_lane(self.world, self.config, self.me["pos"], self.me, self.strong)[0])


if __name__ == "__main__":
    unittest.main()
