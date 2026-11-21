"""Post-kill health/rearm windows and their exact interruption boundaries."""
import copy
import unittest

from test_bot import fixture, flat_world
from sentinel.cover import CoverPlanner
from sentinel.refit import RefitCycle
from sentinel.strategy import Bot


class RefitTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], hp=1050, max_hp=1400,
                       energy=100, grounded=True, in_zone=True)
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, reload=0)
        self.obs.update(t=20, tick=400, alive=12, events=[], mechs=[], projectiles=[])
        self.cycle = RefitCycle(self.config)

    def advance(self, now, events=()):
        self.obs.update(t=now, tick=round(now*20), events=list(events))

    def kill(self, target=5):
        self.obs["events"] = [{"type": "kill", "target": target}]
        self.cycle.update(self.obs)

    @staticmethod
    def enemy(ident=7, distance=100, charging=False):
        return {"id": ident, "kind": "mech", "pos": [distance, 0, 0],
                "vel": [0, 0, 0], "weapons": ["gun", "laser"], "charging": charging}

    def test_true_mech_kill_starts_fixed_window_from_actual_regen_math(self):
        self.kill()
        self.assertTrue(self.cycle.active)
        self.assertEqual(self.cycle.started, 20)
        expected = 20+5+(1260-1050)/45+3
        self.assertAlmostEqual(self.cycle.deadline, expected)
        self.assertTrue(self.cycle.choose(self.obs, []))

    def test_npc_crate_hits_and_loot_never_start_a_refit(self):
        for event in ({"type": "kill", "target": 101}, {"type": "kill", "target": 1001},
                      {"type": "hit", "target": 7, "amount": 45, "weapon": "gun"},
                      {"type": "pickup", "cubes": 2}):
            self.advance(self.obs["t"]+.1, [event])
            self.cycle.update(self.obs)
            self.assertFalse(self.cycle.active)

    def test_nearly_empty_gun_can_trigger_without_missing_health(self):
        self.me["hp"] = 1400
        self.gun["ammo"] = 4
        self.kill()
        self.assertTrue(self.cycle.active)
        self.assertEqual(self.cycle.deadline, 26)
        self.assertTrue(self.cycle.should_reload(self.obs, True, []))

    def test_healthy_ready_and_ordinary_low_health_do_not_start(self):
        for hp, ammo in ((1400, 9), (1400, 5), (800, 1)):
            self.cycle = RefitCycle(self.config)
            self.me["hp"], self.gun["ammo"] = hp, ammo
            self.kill()
            self.assertFalse(self.cycle.active)

    def test_final_duel_or_outside_zone_never_starts(self):
        self.obs["alive"] = 2
        self.kill()
        self.assertFalse(self.cycle.active)
        self.obs["alive"], self.me["in_zone"] = 12, False
        self.advance(21, [{"type": "kill", "target": 5}])
        self.cycle.update(self.obs)
        self.assertFalse(self.cycle.active)

    def test_exact_deadline_and_additional_kills_never_extend_it(self):
        self.kill()
        deadline = self.cycle.deadline
        self.advance(21, [{"type": "kill", "target": 6}])
        self.cycle.update(self.obs)
        self.assertEqual(self.cycle.deadline, deadline)
        self.advance(deadline-.001)
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=True))
        self.advance(deadline)
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=True))
        self.assertIn("deadline", self.cycle.reason)

    def test_duplicate_observation_is_idempotent(self):
        self.kill()
        deadline = self.cycle.deadline
        self.cycle.update(self.obs)
        self.assertEqual(self.cycle.victims, [5])
        self.assertEqual(self.cycle.deadline, deadline)

    def test_residual_victim_bullet_delays_quiet_but_not_fixed_deadline(self):
        self.kill()
        deadline = self.cycle.deadline
        self.advance(20.2, [{"type": "damaged", "by": 5, "weapon": "gun", "amount": 45}])
        self.me["hp"] -= 45
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=True))
        self.assertEqual(self.cycle.deadline, deadline)
        self.assertEqual(self.cycle.last_taken, 20.2)
        self.gun["ammo"] = 2
        self.assertFalse(self.cycle.should_reload(self.obs, True, []))

    def test_new_attacker_damage_ends_cycle_even_before_it_is_visible(self):
        self.kill()
        self.advance(20.2, [{"type": "damaged", "by": 7, "weapon": "gun", "amount": 45}])
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=True))
        self.assertIn("fresh damage", self.cycle.reason)

    def test_completion_needs_health_and_rearmed_gun(self):
        self.gun["ammo"] = 2
        self.kill()
        self.me["hp"] = 1260
        self.advance(26)
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=True))
        self.gun.update(ammo=12, reload=.1)
        self.advance(26.1)
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=True))
        self.gun["reload"] = 0
        self.advance(26.2)
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=True))

    def test_ordinary_recovery_and_predicted_storm_immediately_regain_control(self):
        for kwargs in ({"ordinary_recovery": True}, {"zone_safe": False}):
            self.cycle = RefitCycle(self.config)
            self.kill()
            self.assertFalse(self.cycle.choose(self.obs, [], **kwargs))

    def test_shelter_allows_distant_hunter_but_not_rounding_close_hunter(self):
        self.kill()
        self.obs["mechs"] = [self.enemy(distance=100, charging=True)]
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=True))
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=False))
        self.cycle = RefitCycle(self.config)
        self.kill()
        self.obs["mechs"] = [self.enemy(distance=54)]
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=True))

    def test_exposed_crossfire_cancels_but_dead_victim_is_not_new_pressure(self):
        self.kill()
        self.obs["mechs"] = [self.enemy(5, 30), self.enemy(7, 100)]
        self.assertTrue(self.cycle.choose(self.obs, [], sheltered=False))
        self.obs["mechs"].append(self.enemy(8, 110))
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=False))

    def test_partial_reload_requires_real_shelter_or_quiet_field(self):
        self.gun["ammo"] = 3
        self.kill()
        self.obs["mechs"] = [self.enemy(distance=160)]
        self.assertFalse(self.cycle.should_reload(self.obs, False, []))
        self.assertTrue(self.cycle.should_reload(self.obs, True, []))
        self.obs["mechs"] = []
        self.assertFalse(self.cycle.should_reload(self.obs, False, []))
        self.advance(20.75)
        self.assertTrue(self.cycle.should_reload(self.obs, False, []))
        remembered = [(self.enemy(distance=220), .5)]
        self.assertFalse(self.cycle.should_reload(self.obs, False, remembered))

    def test_bot_does_not_use_ordinary_partial_reload_during_an_exposed_refit(self):
        bot = Bot(self.hello)
        bot.cover = CoverPlanner(flat_world(), self.config)
        self.me["id"], self.gun["ammo"] = 0, 3
        self.obs["zone"].update(center=[0, 0], next_center=[0, 0], radius=400,
                                next_radius=400, shrink_start=90, shrink_end=100)
        self.obs["mechs"] = [dict(self.enemy(distance=205), aim=[3.14, 0], hp=1400)]
        self.obs["events"] = [{"type": "kill", "target": 5}]
        action = bot.act(self.obs)
        self.assertTrue(bot.refit.active)
        self.assertFalse(action["reload"])

    def test_partial_reload_never_starts_at_end_or_during_current_reload(self):
        self.gun["ammo"] = 3
        self.kill()
        self.gun["reload"] = .1
        self.assertFalse(self.cycle.should_reload(self.obs, True, []))
        self.gun["reload"] = 0
        self.advance(self.cycle.deadline-2.4)
        self.assertFalse(self.cycle.should_reload(self.obs, True, []))

    def test_incoming_crossing_projectile_or_drone_denies_partial_reload(self):
        self.gun["ammo"] = 3
        self.kill()
        self.obs["projectiles"] = [{"id": 9, "kind": "gun", "pos": [40, 0, 7], "vel": [-252, 0, 0]}]
        self.assertFalse(self.cycle.should_reload(self.obs, True, []))
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=False))
        self.cycle = RefitCycle(self.config)
        self.obs["projectiles"] = []
        self.kill()
        self.obs["mechs"] = [{"id": 101, "kind": "npc", "pos": [25, 0, 0]}]
        self.assertFalse(self.cycle.should_reload(self.obs, True, []))
        self.assertFalse(self.cycle.choose(self.obs, [], sheltered=False))


if __name__ == "__main__":
    unittest.main()
