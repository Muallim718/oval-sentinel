"""Laser kit acquisition, live corridor safety, range, and upgrade arithmetic."""
import copy
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.laser_doctrine import LaserDoctrine
from sentinel.strategy import Bot
from sentinel.combat import Combat
from sentinel.navigation import Navigator
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.opener import Opener
from sentinel.salvage import KillSalvage


class LaserDoctrineTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[-70, 0, 0], vel=[0, 0, 0], aim=[0, 0], hp=1400,
                       max_hp=1400, energy=100, cubes=0, grounded=True, in_zone=True)
        self.me["weapons"][0].update(ammo=12, reload=0, cooldown=0)
        self.me["weapons"][1] = self.weapon("lightning")
        self.obs.update(t=0, tick=0, alive=16, events=[], mechs=[], projectiles=[],
                        crates=[], cubes=[], drops=[], pickups=[])
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.policy = LaserDoctrine(self.world, self.config)
        self.circle = ([0, 0], 118)

    def weapon(self, kind, **extra):
        return dict(kind=kind, cooldown=0, charge=0,
                    stats=copy.deepcopy(self.config["weapons"][kind]), **extra)

    def laser(self, x=20, y=0, z=0):
        item = dict(id=8001, kind="laser", pos=[x, y, z])
        self.obs["pickups"] = [item]
        return item

    def choose(self, threats=(), recovering=False):
        return self.policy.choose(self.obs, threats, self.circle, recovering=recovering)

    def advance(self, now):
        self.obs.update(t=now, tick=round(now*20), events=[])

    def bot(self):
        bot = Bot(self.hello)
        bot.world = self.world
        bot.nav = Navigator(self.world, self.config["mech"])
        bot.combat = Combat(self.world, self.config)
        bot.cover = CoverPlanner(self.world, self.config)
        bot.motion = GroundSteering(self.world, self.config)
        bot.salvage = KillSalvage(self.world, self.config)
        bot.opener = Opener(self.world, self.config)
        bot.laser_doctrine = self.policy
        return bot

    def test_laser_is_a_real_mission_despite_holding_arc_or_mortar(self):
        self.laser()
        for kind in ("lightning", "mortar"):
            with self.subTest(kind=kind):
                self.me["weapons"][1] = self.weapon(kind)
                self.policy = LaserDoctrine(self.world, self.config)
                mission = self.choose()
                self.assertIsNotNone(mission)
                self.assertEqual((mission.kind, mission.target_id), ("laser", 8001))
                self.assertEqual(mission.waypoint, (20, 0, 0))
                self.assertIsNone(mission.exclusive_target)
                self.assertTrue(mission.sprint)

    def test_selection_remains_available_after_opening_window(self):
        self.advance(90)
        self.laser()
        self.assertIsNotNone(self.choose())

    def test_existing_laser_does_not_initiate_repeated_swaps(self):
        self.laser()
        self.me["weapons"][1] = self.weapon("laser")
        self.assertIsNone(self.choose())
        self.assertFalse(self.policy.pickup_action(self.obs, (), self.circle))

    def test_safe_immediate_swap_preserves_gun_and_replaces_arc(self):
        self.laser(x=-68)
        action = self.bot().act(self.obs)
        self.assertEqual(action["take"], 8001)
        self.assertEqual(action["drop"], 1)
        self.assertEqual(self.me["weapons"][0]["kind"], "gun")
        self.assertEqual(action["fire"], [False, False])

    def test_recent_damage_recovery_and_imminent_hunter_veto_swap(self):
        self.laser(x=-68)
        self.obs["events"] = [dict(type="damaged", amount=45, by=1, weapon="gun", bearing=0)]
        self.assertEqual(self.policy.pickup_action(self.obs, (), self.circle), {})
        self.advance(3)
        self.assertEqual(self.policy.pickup_action(self.obs, (), self.circle, recovering=True), {})
        enemy = dict(id=1, kind="mech", pos=[-10, 0, 0], weapons=["gun"], hp=1400)
        self.obs["mechs"] = [enemy]
        self.assertIsNone(self.choose([(enemy, 1)]))
        self.assertEqual(self.policy.pickup_action(self.obs, [(enemy, 1)], self.circle), {})

    def test_free_nearby_laser_retains_legacy_empty_or_mortar_pickup_while_recovering(self):
        self.laser(x=-68)
        self.me["hp"] = 700
        self.obs["events"] = [dict(type="damaged", amount=45, by=1, weapon="gun", bearing=0)]
        for kind in (None, "mortar"):
            with self.subTest(kind=kind):
                self.me["weapons"][1] = self.weapon(kind) if kind else None
                self.policy = LaserDoctrine(self.world, self.config)
                bot = self.bot()
                without = copy.deepcopy(self.obs)
                without["pickups"] = []
                control = self.bot().act(without)
                action = bot.act(self.obs)
                self.assertEqual(action.get("take"), 8001)
                self.assertEqual(action.get("drop"), 1 if kind else None)
                self.assertEqual(action["move"], control["move"])
                self.assertEqual(action["fire"], control["fire"])
                self.assertFalse(self.policy.pending)

    def test_corridor_cannot_be_certified_from_sheltered_start_alone(self):
        self.world = flat_world([rectangle(-40, -25, -35, 25)])
        self.policy = LaserDoctrine(self.world, self.config)
        self.laser(x=20)
        enemy = dict(id=1, kind="mech", pos=[50, 60, 0], weapons=["gun"], hp=1400)
        self.obs["mechs"] = [enemy]
        threats = [(enemy, 1)]
        self.assertTrue(self.policy._safe_point(self.obs, self.me["pos"], threats, 3))
        for tick in range(20):
            self.advance(tick*.1)
            mission = self.choose(threats)
            self.assertIsNone(mission)
            if not self.policy.pending:
                break
        self.assertFalse(self.policy.pending)
        self.assertIn("corridor", self.policy.reason)

    def test_full_wall_separating_map_rejects_inaccessible_laser(self):
        self.world = flat_world([rectangle(-5, -120, 5, 120)])
        self.policy = LaserDoctrine(self.world, self.config)
        self.laser()
        for tick in range(30):
            self.advance(tick*.1)
            self.assertIsNone(self.choose())
            if not self.policy.pending:
                break
        self.assertFalse(self.policy.pending)
        self.assertIn("route", self.policy.reason)

    def test_roof_weapon_urgent_future_zone_and_final_duel_yield(self):
        self.laser(z=20)
        self.assertIsNone(self.choose())
        self.laser()
        self.circle = ([100, 0], 25)
        self.assertIsNone(self.choose())
        self.circle = ([0, 0], 118)
        self.obs["alive"] = 2
        self.assertIsNone(self.choose())

    def test_no_progress_rejects_fixed_mission_without_refreshing_deadline(self):
        self.laser()
        self.assertIsNotNone(self.choose())
        deadline = self.policy.current["deadline"]
        self.advance(2.9)
        self.assertIsNotNone(self.choose())
        self.assertEqual(self.policy.current["deadline"], deadline)
        self.advance(3)
        self.assertIsNone(self.choose())
        self.assertFalse(self.policy.pending)
        self.assertIn("progress", self.policy.reason)

    def test_live_body_growth_rechecks_route_and_never_resets_nav_growth_flag(self):
        self.laser()
        self.assertIsNotNone(self.choose())
        self.me["stats"]["radius"] *= 1.5
        self.me["stats"]["height"] *= 1.5
        self.advance(.1)
        self.assertIsNotNone(self.choose())
        self.assertTrue(self.policy.nav.body_changed)
        self.assertAlmostEqual(self.policy.route_body[0], self.me["stats"]["radius"])

    def test_held_laser_uses_the_original_committed_duel_range(self):
        self.me["weapons"][1] = self.weapon("laser")
        enemy = dict(id=1, kind="mech", pos=[0, 0, 0], vel=[0, 0, 0],
                     aim=[3.14, 0], hp=1400, max_hp=1400, cubes=0, weapons=["gun"])
        self.obs["mechs"] = [enemy]
        bot = self.bot()
        bot.act(self.obs)
        self.assertEqual(bot.commitment.target_id, 1)
        self.assertEqual(bot.fight_range, 42)
        enemy["hp"] = 300
        self.advance(.1)
        bot.act(self.obs)
        self.assertEqual(bot.fight_range, 42)

if __name__ == "__main__":
    unittest.main()
