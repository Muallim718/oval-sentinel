"""Early duel commitment preserves burst opportunities and yields crossfire."""
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.duel_commitment import DuelCommitment


class DuelCommitmentTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.world = flat_world()
        self.controller = DuelCommitment(hello["config"])
        self.me = self.obs["self"]
        self.me.update(id=0, pos=[-50, 0, 0], hp=1400, max_hp=1400,
                       grounded=True, in_zone=True, energy=100)
        self.enemy = dict(id=1, kind="mech", hp=1400, max_hp=1400, cubes=0,
                          pos=[50, 0, 0], aim=[3.14, 0], weapons=["gun"])
        self.obs.update(t=30, alive=16, mechs=[self.enemy], events=[])

    def choose(self, circle=((0, 0), 116)):
        return self.controller.choose(self.obs, [(enemy, 1.0) for enemy in self.obs["mechs"]],
                                      circle, self.world)

    def test_closes_an_isolated_even_fight_and_stays_through_ordinary_retreat_health(self):
        plan = self.choose()
        self.assertEqual(plan.enemy["id"], 1)
        self.assertAlmostEqual(plan.range, 42)
        self.assertTrue(plan.sprint)
        self.me["hp"], self.enemy["hp"] = 700, 820
        self.assertIsNotNone(self.choose())
        self.me["hp"] = 550
        self.assertIsNone(self.choose())

    def test_lower_health_finish_requires_a_clear_advantage(self):
        self.me["hp"], self.enemy["hp"] = 490, 395
        self.assertIsNone(self.choose())
        self.enemy["hp"] = 300
        self.assertIsNotNone(self.choose())

    def test_hands_back_immediately_when_two_enemies_can_fight(self):
        self.assertIsNotNone(self.choose())
        second = dict(self.enemy, id=2, pos=[-23, 72, 0])
        self.obs["mechs"].append(second)
        self.assertIsNone(self.choose())

    def test_actual_damage_from_unseen_second_threat_ends_commitment(self):
        self.assertIsNotNone(self.choose())
        self.obs["t"] += .1
        self.obs["events"] = [{"type": "damaged", "by": 2, "weapon": "gun", "amount": 45}]
        self.assertIsNone(self.choose())

    def test_requires_safe_zone_and_a_clear_ballistic_lane(self):
        self.assertIsNone(self.choose(circle=((0, 0), 54)))
        self.world = flat_world([rectangle(-3, -15, 3, 15)])
        self.assertIsNone(self.choose())

    def test_does_not_close_into_lightning_when_we_have_no_arc(self):
        self.enemy["weapons"].append("lightning")
        self.enemy["pos"] = [25, 0, 0]
        plan = self.choose()
        self.assertEqual(plan.range, 64)
        self.assertFalse(plan.sprint)

    def test_late_and_last_round_empty_mag_fall_back(self):
        self.obs["alive"] = 8
        self.assertIsNone(self.choose())
        self.obs["alive"] = 12
        self.enemy["pos"] = [-25, 0, 0]
        self.me["weapons"][0].update(ammo=0, reload=1.2)
        self.assertIsNone(self.choose())


if __name__ == "__main__":
    unittest.main()
