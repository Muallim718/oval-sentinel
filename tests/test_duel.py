"""Ranges and sprints depend on usable weapon, relative motion, and energy."""
import copy
import unittest
from test_bot import fixture
from sentinel.duel import duel_envelope


class DuelEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.hello, obs = fixture()
        self.config = self.hello["config"]
        self.me = obs["self"]
        self.me.update(pos=[0, 0, 0], hp=1400, energy=100, vel=[0, 0, 0])
        self.enemy = {"id": 1, "pos": [110, 0, 0], "vel": [0, 0, 0],
                      "hp": 1400, "weapons": ["gun"]}

    def secondary(self, kind):
        self.me["weapons"][1] = {"kind": kind, "cooldown": 0, "charge": 0,
                                   "stats": copy.deepcopy(self.config["weapons"][kind])}

    def envelope(self):
        return duel_envelope(self.me, self.enemy, self.config)

    def test_gun_uses_projectile_standoff_instead_of_65_meter_chase(self):
        distance, sprint = self.envelope()
        self.assertGreaterEqual(distance, 100)
        self.assertLessEqual(distance, 110)
        self.assertFalse(sprint)

    def test_ready_lightning_already_in_range_keeps_damage_without_sprint(self):
        self.secondary("lightning")
        self.enemy["pos"] = [40, 0, 0]
        distance, sprint = self.envelope()
        self.assertLess(distance, self.me["weapons"][1]["stats"]["range"])
        self.assertFalse(sprint)

    def test_healthy_lightning_makes_short_energy_feasible_lunge(self):
        self.secondary("lightning")
        self.enemy["pos"] = [70, 0, 0]
        distance, sprint = self.envelope()
        self.assertLess(distance, 45)
        self.assertTrue(sprint)

    def test_far_or_receding_target_does_not_provoke_doomed_lightning_chase(self):
        self.secondary("lightning")
        for position, velocity in ((150, 0), (80, 11.7), (60, 19.5)):
            with self.subTest(position=position, velocity=velocity):
                self.enemy.update(pos=[position, 0, 0], vel=[velocity, 0, 0])
                distance, sprint = self.envelope()
                self.assertGreaterEqual(distance, 95)
                # At <75m an escaping sprint may be useful even when chasing is
                # impossible. An enemy receding from us needs no escape sprint.
                self.assertFalse(sprint)

    def test_lightning_lunge_requires_health_readiness_and_firing_reserve(self):
        self.secondary("lightning")
        self.enemy["pos"] = [60, 0, 0]
        self.me["hp"] = 700
        self.assertGreaterEqual(self.envelope()[0], 95)
        self.me.update(hp=1400, energy=45)
        self.assertGreaterEqual(self.envelope()[0], 95)
        self.me["energy"] = 100
        self.me["weapons"][1]["cooldown"] = 1
        self.assertGreaterEqual(self.envelope()[0], 95)

    def test_mortar_counter_does_not_invite_out_of_range_lightning_lunge(self):
        self.secondary("lightning")
        self.enemy.update(pos=[60, 0, 0], weapons=["gun", "mortar"])
        self.assertGreaterEqual(self.envelope()[0], 95)

    def test_laser_spacing_preserves_cookoff_and_stays_outside_lightning(self):
        self.secondary("laser")
        self.enemy["weapons"] = ["gun", "mortar"]
        self.assertGreaterEqual(self.envelope()[0], 130)
        self.enemy["weapons"] = ["gun", "lightning"]
        self.assertGreaterEqual(self.envelope()[0], 110)

    def test_close_gun_pursuit_uses_sprint_to_buy_separation(self):
        self.enemy.update(pos=[60, 0, 0], vel=[-11.7, 0, 0])
        self.assertTrue(self.envelope()[1])
        self.me["energy"] = 40
        self.assertFalse(self.envelope()[1])

    def test_charging_slowdown_and_faster_pursuer_prevent_false_escape_promise(self):
        self.secondary("laser")
        self.me["weapons"][1]["charge"] = .5
        self.enemy.update(pos=[60, 0, 0], vel=[-11.7, 0, 0])
        self.assertFalse(self.envelope()[1])
        self.me["weapons"][1]["charge"] = 0
        self.assertTrue(self.envelope()[1])
        self.enemy["vel"][0] = -25
        self.assertFalse(self.envelope()[1])

    def test_low_energy_lightning_still_preserves_immediate_one_arc_finish(self):
        self.secondary("lightning")
        self.me["energy"] = 12
        self.enemy.update(pos=[30, 0, 0], hp=40)
        distance, sprint = self.envelope()
        self.assertLess(distance, 45)
        self.assertFalse(sprint)

    def test_existing_motion_changes_lunge_feasibility_without_torso_assumptions(self):
        self.secondary("lightning")
        self.enemy["pos"] = [80, 0, 0]
        self.me["energy"] = 95
        self.me["vel"] = [19.5, 0, 0]
        self.assertTrue(self.envelope()[1])
        self.me["vel"] = [-19.5, 0, 0]
        self.assertFalse(self.envelope()[1])


if __name__ == "__main__":
    unittest.main()
