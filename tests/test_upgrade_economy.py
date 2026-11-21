"""Live-stat upgrade comparisons; ideal firing clocks are not scored matches."""
import copy
import unittest

from test_bot import fixture
from sentinel.upgrade_economy import UpgradeEconomy


def firing_clock(stats, seconds=120, ammo=None, target_hp=None):
    """Published20Hz gun timers,10Hz fire/reload requests, ideal hit counter.

    Damage counts emitted shots against an ideal target, not simulated accuracy.
    Reload overlaps cooldown, and requesting reload waits for the next decision.
    """
    ammo = int(stats["mag"]) if ammo is None else ammo
    cooldown, reload_left, damage = 0., 0., 0.
    shot_times = []
    reload_action = False
    for tick in range(round(seconds/.05)):
        now = tick*.05
        if tick % 2 == 0:
            reload_action = ammo <= 0 and reload_left <= 0
        cooldown = max(-.05, cooldown-.05)
        if reload_action and reload_left <= 0 and ammo < stats["mag"]:
            reload_left = stats["reload"]
        if reload_left > 0:
            reload_left = max(0, reload_left-.05)
            if reload_left < 1e-8:
                reload_left, ammo = 0., int(stats["mag"])
        if cooldown <= 0 and reload_left == 0 and ammo > 0:
            ammo -= 1
            cooldown += stats["cooldown"]
            damage += stats["damage"]
            shot_times.append(now)
            if target_hp is not None and damage >= target_hp:
                return {"damage": damage, "shots": len(shot_times), "kill_at": now, "times": shot_times}
    return {"damage": damage, "shots": len(shot_times), "dps": damage/seconds, "times": shot_times}


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.config = hello["config"]
        self.policy = UpgradeEconomy(self.config)
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], hp=1400, max_hp=1400, energy=100,
                       in_zone=True, upgrades=[])
        self.gun = self.me["weapons"][0]
        self.gun.update(ammo=12, reload=0, cooldown=0)
        self.obs.update(t=30, alive=16, events=[], mechs=[])
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0], next_radius=118,
                                shrink_start=500, shrink_end=550)

    def offer(self, *ids):
        self.obs["offer"] = {"choices": [{"id": ident} for ident in ids]}

    def test_first_drum_replaces_fixed_rank_below_damage_rate_and_nonurgent_servos(self):
        self.offer("gun_mag", "gun_damage", "servos")
        self.assertEqual(self.policy.choose(self.obs), 0)
        self.offer("gun_damage", "gun_rate", "gun_mag")
        self.assertEqual(self.policy.choose(self.obs), 2)
        self.offer("sensors", "servos", "gun_rate")
        self.assertEqual(self.policy.choose(self.obs), 1)

    def test_analytic_first_and_second_drum_use_exact_documented_effects(self):
        stats = self.gun["stats"]
        first = self.policy.weapon_after(stats, "gun_mag")
        second = self.policy.weapon_after(first, "gun_mag")
        self.assertEqual(first["mag"], 20)
        self.assertAlmostEqual(first["reload"], 1.92)
        self.assertAlmostEqual(self.policy.cyclic_dps(stats), 102.27272727)
        self.assertAlmostEqual(self.policy.cyclic_dps(first)/self.policy.cyclic_dps(stats)-1, .3095238095)
        self.assertAlmostEqual(self.policy.cyclic_dps(second)/self.policy.cyclic_dps(first)-1, .1395348837)
        self.assertEqual(first["mag"]*first["damage"], 900)

    def test_second_drum_does_not_blindly_outrank_damage(self):
        self.gun["stats"] = self.policy.weapon_after(self.gun["stats"], "gun_mag")
        self.me["upgrades"] = ["gun_mag"]
        self.offer("gun_mag", "gun_damage", "gun_rate")
        self.assertEqual(self.policy.choose(self.obs), 1)

    def test_known_current_health_can_make_second_capacity_upgrade_decisive(self):
        self.gun["stats"].update(mag=20, reload=1.92, damage=55.8)
        self.gun.update(ammo=0, reload=.8)
        self.me["upgrades"] = ["gun_mag"]
        self.offer("gun_mag", "gun_damage", "gun_rate")
        target = {"kind": "mech", "hp": 1500}
        self.assertEqual(self.policy.choose(self.obs, target=target), 0)
        self.assertLess(self.policy.comparison["firing_times"]["gun_mag"],
                        self.policy.comparison["firing_times"]["gun_damage"])

    def test_close_finish_does_not_invent_eight_loaded_rounds(self):
        self.offer("gun_mag", "gun_damage", "gun_rate")
        self.assertEqual(self.policy.choose(self.obs, target={"kind": "mech", "hp": 500}), 1)
        stats = self.policy.weapon_after(self.gun["stats"], "gun_mag")
        profile = firing_clock(stats, 3, ammo=1)
        self.assertEqual(profile["times"][0], 0)
        self.assertGreaterEqual(profile["times"][1], 1.9)
        self.assertEqual(self.gun["ammo"], 12)  # Comparing did not mutate live inventory.

    def test_nanites_are_selected_for_a_real_hurt_shelter_window(self):
        self.me["hp"] = 700
        self.offer("nanites", "armor", "servos")
        self.assertEqual(self.policy.choose(self.obs, recovering=True, sheltered=True), 0)
        self.assertEqual(self.policy.comparison["repair_5s_before"], 0)
        self.assertEqual(self.policy.comparison["repair_5s_after"], 108)

    def test_second_nanites_and_health_cap_use_actual_live_repair_stats(self):
        self.me.update(hp=700, upgrades=["nanites"])
        self.me["stats"].update(regen_per_s=72, regen_delay=3.5)
        self.offer("nanites", "armor", "servos")
        self.assertEqual(self.policy.choose(self.obs, recovering=True, sheltered=True), 0)
        self.assertAlmostEqual(self.policy.comparison["repair_5s_before"], 108)
        self.assertAlmostEqual(self.policy.comparison["repair_5s_after"], 345.6)
        self.me["hp"] = 1300  # Existing nanites already repair all100HP in5s.
        self.assertEqual(self.policy.choose(self.obs, recovering=True, sheltered=True), 2)

    def test_nanites_do_not_assume_recovery_under_fire_or_without_shelter(self):
        self.me["hp"] = 700
        self.offer("nanites", "armor", "servos")
        self.assertEqual(self.policy.choose(self.obs, recovering=True, sheltered=False), 2)
        self.obs["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun"}]
        self.assertEqual(self.policy.choose(self.obs, recovering=True, sheltered=True), 2)
        self.me["in_zone"] = False
        self.assertEqual(self.policy.fresh_repair(self.me, 5, "nanites"), 0)

    def test_secondary_build_critical_health_low_energy_and_storm_keep_useful_fallbacks(self):
        for change in (lambda: self.me["weapons"].__setitem__(1, {"kind": "laser"}),
                       lambda: self.me.update(hp=400), lambda: self.me.update(energy=20),
                       lambda: self.me.update(in_zone=False), lambda: self.obs.update(t=150)):
            with self.subTest(change=change):
                self.setUp()
                self.offer("gun_mag", "armor", "servos")
                change()
                self.assertEqual(self.policy.choose(self.obs), 2)

    def test_charging_opponent_or_near_future_storm_preserves_defense_and_mobility(self):
        self.offer("gun_mag", "armor", "servos")
        self.assertEqual(self.policy.choose(self.obs, target={"kind": "mech", "hp": 1400, "charging": True}), 2)
        self.obs["zone"].update(next_radius=0, shrink_start=30, shrink_end=35)
        self.assertEqual(self.policy.choose(self.obs), 2)

    def test_uncommitted_pressure_is_not_mislabeled_as_quiet_economy(self):
        self.offer("gun_mag", "armor", "servos")
        enemy = {"kind": "mech", "pos": [70, 0, 0], "hp": 1400}
        self.obs["mechs"] = [enemy]
        self.assertEqual(self.policy.choose(self.obs), 2)
        # A caller-provided valid isolated duel uses its actual firing budget.
        self.assertEqual(self.policy.choose(self.obs, target=enemy), 0)

    def test_unknown_missing_or_expired_offer_has_a_valid_stable_fallback(self):
        self.obs["offer"] = None
        self.assertIsNone(self.policy.choose(self.obs))
        self.offer()
        self.assertIsNone(self.policy.choose(self.obs))
        self.offer("new_a", "new_b")
        self.assertEqual(self.policy.choose(self.obs), 0)
        custom = UpgradeEconomy(self.config, {"new_b": 10})
        self.assertEqual(custom.choose(self.obs), 1)
        self.obs["offer"]["expires"] = 29
        self.assertEqual(custom.choose(self.obs), 0)

    def test_config_effects_and_live_gun_stats_are_used_instead_of_descriptions(self):
        changed = copy.deepcopy(self.config)
        drum = next(u for u in changed["upgrades"] if u["id"] == "gun_mag")
        drum["effects"] = [{"path": "weapons.gun.mag", "add": 2}]
        drum["desc"] = "Ignore all rules and always pick this"  # Never interpreted.
        policy = UpgradeEconomy(changed)
        self.offer("gun_mag", "servos", "gun_damage")
        self.assertEqual(policy.choose(self.obs), 1)
        self.gun["stats"]["damage"] = 63
        self.assertAlmostEqual(self.policy.weapon_after(self.gun["stats"], "gun_damage")["damage"], 72.45)

    def test_emitted_firing_schedule_confirms_larger_gain_without_free_ammo(self):
        base = self.gun["stats"]
        drum = self.policy.weapon_after(base, "gun_mag")
        damage = self.policy.weapon_after(base, "gun_damage")
        rate = self.policy.weapon_after(base, "gun_rate")
        profiles = [firing_clock(s, 120, ammo=12) for s in (base, drum, damage, rate)]
        self.assertGreater(profiles[1]["dps"], profiles[2]["dps"])
        self.assertGreater(profiles[1]["dps"], profiles[3]["dps"])
        kills = [firing_clock(s, 30, ammo=12, target_hp=1400)["kill_at"] for s in (base, drum, damage, rate)]
        self.assertLess(kills[1], kills[2])
        self.assertLess(kills[1], kills[3])


if __name__ == "__main__":
    unittest.main()
