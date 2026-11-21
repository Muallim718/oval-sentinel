"""Recovery self-defense without turning the escape into a charged-weapon duel."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.navigation import Navigator
from sentinel.strategy import Bot
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.provisioning import Provisioner


class ReturnFireTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.bot = Bot(self.hello)
        self.world = flat_world()
        self.bot.world = self.world
        self.bot.nav = Navigator(self.world, self.hello["config"]["mech"])
        self.bot.combat = Combat(self.world, self.hello["config"])
        self.bot.cover = CoverPlanner(self.world, self.hello["config"])
        self.bot.provision = Provisioner(self.world, self.hello["config"])
        self.bot.motion = GroundSteering(self.world, self.hello["config"])
        self.me = self.obs["self"]
        self.me.update(pos=[-70, 0, 0], vel=[0, 0, 0], hp=700, aim=[0, 0])
        self.obs.update(t=10, tick=200, alive=16, events=[], mechs=[], projectiles=[],
                        crates=[], cubes=[], pickups=[], drops=[], offer=None)
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.enemy = {"id": 1, "kind": "mech", "pos": [0, 0, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                      "max_hp": 1400, "weapons": ["gun"]}
        self.obs["mechs"] = [self.enemy]
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, reload=0, cooldown=0)
        self.me["aim"] = self.bot.combat.solve(self.me, self.enemy, self.gun)[0]

    def damage(self, weapon="gun"):
        self.obs["events"] = [{"type": "damaged", "amount": 45,
                               "weapon": weapon, "bearing": 0,
                               "by": None if weapon == "zone" else 1}]

    def test_attacked_recovering_bot_fires_gun_and_keeps_escaping(self):
        self.damage()
        action = self.bot.act(self.obs)
        self.assertEqual(action["fire"], [True, False])
        self.assertEqual(self.bot.mode, "recover")
        self.assertIsNone(self.bot.duel)
        self.assertLess(action["move"][0], 0)
        self.assertTrue(action["boost"])

    def test_quiet_recovery_and_outgoing_hits_do_not_start_return_fire(self):
        self.assertEqual(self.bot.act(self.obs)["fire"], [False, False])
        self.obs["events"] = [{"type": "hit", "target": 1, "amount": 45,
                               "weapon": "gun"}]
        self.assertEqual(self.bot.act(self.obs)["fire"], [False, False])

    def test_zone_damage_does_not_start_optional_fight(self):
        self.damage("zone")
        self.assertEqual(self.bot.act(self.obs)["fire"], [False, False])

    def test_return_fire_expires_after_one_second_without_incoming_hits(self):
        self.damage()
        self.assertTrue(self.bot.act(self.obs)["fire"][0])
        self.obs.update(t=10.9, tick=218, events=[])
        self.assertTrue(self.bot.act(self.obs)["fire"][0])
        self.obs.update(t=11.0, tick=220)
        self.assertEqual(self.bot.act(self.obs)["fire"], [False, False])
        self.assertTrue(self.bot.recovering)

    def test_misaligned_empty_and_reloading_guns_do_not_fire(self):
        self.damage()
        self.me["aim"] = [math.pi, 0]
        self.assertFalse(self.bot.act(self.obs)["fire"][0])
        self.me["aim"] = self.bot.combat.solve(self.me, self.enemy, self.gun)[0]
        self.gun["ammo"] = 0
        action = self.bot.act(self.obs)
        self.assertFalse(action["fire"][0])
        self.assertTrue(action["reload"])
        self.gun.update(ammo=12, reload=1.2)
        self.assertFalse(self.bot.act(self.obs)["fire"][0])

    def test_secondary_weapons_are_not_started_during_return_fire(self):
        self.damage()
        for kind in ("laser", "mortar", "lightning"):
            with self.subTest(kind=kind):
                self.me["weapons"][1] = {
                    "kind": kind, "charge": 0, "cooldown": 0,
                    "stats": copy.deepcopy(self.hello["config"]["weapons"][kind])}
                self.assertEqual(self.bot.act(self.obs)["fire"], [True, False])

    def test_cover_range_and_passive_targets_still_block_return_fire(self):
        combat = Combat(flat_world([rectangle(-40, -20, -35, 20)]),
                        self.hello["config"])
        self.assertIsNone(combat.action(self.me, [self.enemy], True, False, True)[2])
        self.enemy["pos"][0] = 500
        self.assertIsNone(self.bot.combat.action(
            self.me, [self.enemy], True, False, True)[2])
        npc = {**self.enemy, "id": 101, "kind": "npc", "pos": [0, 0, 0]}
        crate = {"id": 1001, "pos": [0, 0, 0], "hp": 300}
        self.assertIsNone(self.bot.combat.action(
            self.me, [npc, crate], True, False, True)[2])

    def test_recent_damage_does_not_change_healthy_combat(self):
        self.me["hp"] = self.me["max_hp"]
        ordinary = self.bot.combat.action(self.me, [self.enemy], False, False)
        defended = self.bot.combat.action(self.me, [self.enemy], False, False, True)
        self.assertEqual(ordinary, defended)

    def test_weapon_clock_fires_during_pressure_then_allows_quiet_recovery(self):
        # Only a stationary aiming and gun-clock model, not a scored game. Hits
        # keep recovery unavailable for 8 s; after that the exception must expire.
        rounds = 0
        last_trigger = None
        for decision in range(100):
            self.obs.update(t=10+decision*.1, tick=200+decision*2, events=[])
            if decision < 80 and decision % 5 == 0:
                self.damage()
            action = self.bot.act(self.obs)
            self.me["aim"] = action["aim"]
            if action["fire"][0]:
                last_trigger = self.obs["t"]
            if action.get("reload") and self.gun["reload"] == 0:
                self.gun["reload"] = self.gun["stats"]["reload"]
            for _ in range(2):
                was_reloading = self.gun["reload"] > 0
                self.gun["reload"] = max(0, self.gun["reload"]-.05)
                self.gun["cooldown"] = max(0, self.gun["cooldown"]-.05)
                if was_reloading and self.gun["reload"] == 0:
                    self.gun["ammo"] = self.gun["stats"]["mag"]
                if (action["fire"][0] and self.gun["ammo"] > 0 and
                        self.gun["reload"] == 0 and self.gun["cooldown"] <= 1e-8):
                    rounds += 1
                    self.gun["ammo"] -= 1
                    self.gun["cooldown"] = self.gun["stats"]["cooldown"]
        self.assertGreaterEqual(rounds, 20)
        self.assertLess(last_trigger, 18.5)
        self.assertEqual(action["fire"], [False, False])


if __name__ == "__main__":
    unittest.main()
