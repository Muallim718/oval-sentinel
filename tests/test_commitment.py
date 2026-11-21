"""Observed-trade commitment, including an independent finite-ammo hit clock."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.commitment import State


class CommitmentTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.combat = Combat(self.world, self.config)
        self.me = self.obs["self"]
        self.me.update(id=0, pos=[-70, 0, 0], vel=[0, 0, 0], hp=825,
                       max_hp=1400, cubes=0, aim=[0, 0], in_zone=True)
        self.gun = {"kind": "gun", "ammo": 12, "reload": 0, "cooldown": 0,
                    "stats": copy.deepcopy(self.config["weapons"]["gun"])}
        self.me["weapons"] = [self.gun, None]
        self.enemy = {"id": 1, "kind": "mech", "pos": [-5, 0, 0],
                      "vel": [0, 0, 0], "hp": 380, "max_hp": 1400,
                      "weapons": ["gun"], "cubes": 0}
        self.obs.update(t=0, tick=0, events=[], beams=[], mechs=[self.enemy])
        self.state = State(self.config)
        self.me["aim"] = self.combat.solve(self.me, self.enemy, self.gun)[0]

    def push(self, now, events=(), ammo=None, hp=None, enemy_hp=None, beams=()):
        self.obs.update(t=now, tick=round(now*20), events=list(events), beams=list(beams))
        if ammo is not None:
            self.gun["ammo"] = ammo
        if hp is not None:
            self.me["hp"] = hp
        if enemy_hp is not None:
            self.enemy["hp"] = enemy_hp
        self.state.update(self.obs)

    def hit(self):
        return {"type": "hit", "weapon": "gun", "target": 1, "amount": 45}

    def choose(self, **kwargs):
        return self.state.choose(self.obs, can_hit=lambda target, weapon:
                                 self.combat.solve(self.me, target, weapon), **kwargs)

    def favorable_trade(self, starting_ammo=12):
        # Four gun rounds fired at 20 Hz-compatible times .05/.30/.55/.80
        # arrive after a 65/252 s flight. Only one incoming 45-damage hit.
        self.push(0, ammo=starting_ammo)
        self.push(.1, [{"type": "damaged", "weapon": "gun", "by": 1,
                         "amount": 45}], ammo=starting_ammo-1, hp=780)
        self.push(.4, [self.hit()], ammo=starting_ammo-2, enemy_hp=335)
        self.push(.6, [self.hit()], ammo=starting_ammo-3, enemy_hp=290)
        self.push(.8, [self.hit()], ammo=starting_ammo-4, enemy_hp=245)
        self.push(1.1, [self.hit()], enemy_hp=200)
        self.push(1.2)

    def test_ready_gun_can_finish_a_durable_trade_below_fixed_retreat_threshold(self):
        self.favorable_trade()
        self.assertLess(self.me["hp"]/self.me["max_hp"], .58)
        self.assertGreater(self.enemy["hp"], 170)
        self.assertIs(self.choose(), self.enemy)
        self.assertEqual(self.state.weapon_kind, "gun")
        self.assertLess(self.state.horizon, 2)
        self.assertGreater(self.me["hp"]-self.state.incoming_budget, 280)

    def test_no_attributed_damage_evidence_does_not_create_static_matchup_commitment(self):
        self.enemy["hp"] = 200
        self.me["hp"] = 1100
        self.push(1.2)
        self.assertIsNone(self.choose())
        self.push(1.4, [{"type": "hit", "weapon": "gun", "target": 101, "amount": 45}])
        self.push(1.8, [{"type": "hit", "weapon": "gun", "target": 1001, "amount": 300}])
        self.assertIsNone(self.choose())

    def test_insufficient_ammo_reload_or_long_kill_horizon_vetoes_gun_commitment(self):
        self.favorable_trade()
        self.gun["ammo"] = 2
        self.assertIsNone(self.choose())
        self.gun.update(ammo=8, reload=1)
        self.assertIsNone(self.choose())
        self.gun["reload"] = 0
        self.enemy["hp"] = 900
        self.assertIsNone(self.choose())

    def test_losing_actual_trade_vetoes_a_ready_short_burst(self):
        self.favorable_trade()
        self.push(1.25, [{"type": "damaged", "weapon": "gun", "by": 1,
                          "amount": 180}], hp=600)
        self.assertIsNone(self.choose())

    def test_ready_charged_lethal_laser_needs_no_unproven_future_charge(self):
        laser = {"kind": "laser", "charge": .75, "cooldown": 0,
                 "stats": copy.deepcopy(self.config["weapons"]["laser"])}
        self.me["weapons"] = [None, laser]
        self.enemy["hp"] = 200
        self.me["hp"] = 700
        self.me["aim"] = self.combat.solve(self.me, self.enemy, laser)[0]
        self.push(1)
        self.assertIs(self.choose(), self.enemy)
        self.assertEqual(self.state.weapon_kind, "laser")
        self.assertLess(self.state.horizon, .2)
        self.state.cancel()
        laser["charge"] = 0
        self.assertIsNone(self.choose())

    def test_observed_laser_cooldown_distinguishes_a_real_counter_burst_window(self):
        self.favorable_trade()
        self.enemy["weapons"] = ["gun", "laser"]
        self.assertIsNone(self.choose())
        self.push(1.25, beams=[{"kind": "laser", "by": 1, "age": 0,
                                "path": [[-5, 0, 7], [-70, 0, 4.5]]}])
        self.assertIs(self.choose(), self.enemy)
        self.assertEqual(self.state.weapon_kind, "gun")

    def test_second_credible_lane_vetoes_but_a_blocked_lane_is_not_invented_crossfire(self):
        self.favorable_trade()
        second = {**self.enemy, "id": 2, "pos": [-10, 20, 0], "hp": 1400}
        self.obs["mechs"].append(second)
        self.assertIsNone(self.choose())
        self.world = flat_world([rectangle(-40, 5, -35, 50)])
        self.combat = Combat(self.world, self.config)
        exposed = lambda e: self.world.line_clear([*e["pos"][:2], 7], [-70, 0, 4.5])
        self.assertFalse(exposed(second))
        self.assertIs(self.choose(exposed=exposed), self.enemy)

    def test_zone_missing_geometry_and_projectile_pressure_override_trade_proof(self):
        self.favorable_trade()
        self.assertIsNone(self.choose(zone_safe=False))
        self.assertIsNone(self.state.choose(self.obs))
        self.assertIsNone(self.choose(projectile_damage=500))

    def test_recent_unknown_or_npc_attacker_vetoes_a_single_enemy_finish(self):
        self.favorable_trade()
        self.push(1.3, [{"type": "damaged", "weapon": "npc", "by": 101,
                         "amount": 25}], hp=755)
        self.assertIsNone(self.choose())

    def test_cancel_ends_forced_weapon_window_and_unconfirmed_credit(self):
        self.favorable_trade()
        self.assertIsNotNone(self.choose())
        self.push(1.3, ammo=7)
        self.assertTrue(self.state.pending)
        self.state.cancel("sheltered recovery regained control")
        self.assertIsNone(self.state.target_id)
        self.assertIsNone(self.state.weapon_kind)
        self.assertFalse(self.state.pending)
        self.push(1.4, ammo=6)
        self.assertFalse(self.state.pending)

    def test_duplicate_updates_do_not_inflate_trade_and_deadline_cannot_extend_forever(self):
        self.favorable_trade()
        self.assertIsNotNone(self.choose())
        deadline = self.state.deadline
        count = len(self.state.hits)
        self.state.update(self.obs)
        self.assertEqual(len(self.state.hits), count)
        self.push(1.3)
        self.assertIsNotNone(self.choose())
        self.assertEqual(self.state.deadline, deadline)
        self.push(deadline+.01)
        self.assertIsNone(self.choose())
        self.assertIsNone(self.choose())

    def test_finite_ammo_commitment_survives_real_projectile_latency_until_confirmed_kill(self):
        self.favorable_trade(starting_ammo=9)  # Five rounds remain, all five are needed.
        self.assertIsNotNone(self.choose())
        projectiles, queued = [], []
        killed = False
        self.gun["cooldown"] = 0
        for decision in range(1, 21):
            now = 1.2+decision*.1
            self.push(now, queued)
            queued = []
            if self.enemy["hp"] <= 0:
                killed = True
                self.assertIsNone(self.state.target_id)
                break
            self.assertIsNotNone(self.choose(), f"abandoned valid burst at {now}")
            for substep in range(2):
                tick = now+(substep+1)*.05
                self.gun["cooldown"] -= .05
                if self.gun["ammo"] > 0 and self.gun["cooldown"] <= 1e-9:
                    self.gun["ammo"] -= 1
                    self.gun["cooldown"] += self.gun["stats"]["cooldown"]
                    projectiles.append(tick+65/self.gun["stats"]["speed"])
                    if self.gun["ammo"] == 0:
                        self.gun["reload"] = self.gun["stats"]["reload"]
                due = [arrival for arrival in projectiles if arrival <= tick]
                projectiles = [arrival for arrival in projectiles if arrival > tick]
                for _ in due:
                    self.enemy["hp"] -= self.gun["stats"]["damage"]
                    queued.append(self.hit())
                    if self.enemy["hp"] <= 0:
                        queued.append({"type": "kill", "target": 1})
        self.assertTrue(killed)
        self.assertEqual(self.gun["ammo"], 0)
        self.assertLess(now-1.2, 2)

    def test_pending_missed_rounds_expire_and_event_ledgers_stay_bounded(self):
        self.favorable_trade()
        self.assertIsNotNone(self.choose())
        self.push(1.3, ammo=7)
        self.assertTrue(self.state.pending)
        self.push(2)
        self.assertFalse(self.state.pending)
        self.push(2.1, [self.hit() for _ in range(200)])
        self.assertLessEqual(len(self.state.hits), 96)
        self.assertLessEqual(len(self.state.gun_shots), 64)
        self.assertLessEqual(len(self.state.pending), 32)


if __name__ == "__main__":
    unittest.main()
