"""Announced landing, checked travel and four-second capture contracts."""
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.drops import TimedDrop
from sentinel.geometry import distance, unit
from sentinel.navigation import Navigator
from sentinel.movement import GroundSteering
from sentinel.strategy import Bot


class DropTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.world.bounds = {"minX": -400, "maxX": 400, "minY": -200, "maxY": 200}
        self.me = self.obs["self"]
        self.me.update(pos=[-100, 0, 0], vel=[0, 0, 0], hp=700, max_hp=1400,
                       energy=100, max_energy=100, grounded=True, in_zone=True)
        self.drop = {"id": 20000, "pos": [200, 0, 0], "radius": 8, "lands_in": 25,
                     "capture_s": 4, "progress": 0, "holder": None}
        self.obs.update(t=70, tick=1400, alive=16, mechs=[], events=[], projectiles=[],
                        crates=[], pickups=[], cubes=[], drops=[self.drop])
        self.obs["zone"].update(center=[0, 0], radius=380, next_center=[0, 0], next_radius=380,
                                shrink_start=200, shrink_end=250)
        self.circle = ([0, 0], 380)
        self.planner = TimedDrop(self.world, self.config)

    def choose(self, threats=(), recovering=True):
        return self.planner.choose(self.obs, list(threats), self.circle, recovering=recovering)

    def advance(self, now):
        self.obs.update(t=now, tick=round(now*20), events=[])
        self.drop["lands_in"] = max(0, 95-now)

    def enemy(self, x):
        return {"id": 1, "kind": "mech", "pos": [x, 0, 0], "vel": [-8, 0, 0],
                "aim": [math.pi, 0], "weapons": ["gun"], "hp": 1400}

    def test_no_preannouncement_or_final_duel_invented_objective(self):
        self.obs["t"] = 60
        self.assertIsNone(self.choose())
        self.advance(70)
        self.obs["drops"] = []
        self.assertIsNone(self.choose())
        self.obs["drops"] = [self.drop]
        self.obs["alive"] = 2
        self.assertIsNone(self.choose())

    def test_long_announced_route_begins_before_legacy_last_eight_second_gate(self):
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertEqual(self.planner.state, "approach")
        self.assertGreater(distance(self.me["pos"], mission.goal), 150)
        self.assertGreater(self.drop["lands_in"], 8)
        self.assertLessEqual(mission.capture_at, 99.1)
        self.assertTrue(mission.sprint)
        # Exercise the actual selected baseline goal function on this same
        # observation. Its150m/last8s gate excludes this repair objective.
        bot = Bot(self.hello)
        bot.world, bot.nav = self.world, self.planner.nav
        bot.mode, bot.goal = "recover", None
        _, kind, _ = bot.choose_goal(self.obs, True, [])
        self.assertNotEqual(kind, "drop")

    def test_nearby_drop_is_scheduled_instead_of_twenty_five_second_open_camp(self):
        self.drop["pos"] = [0, 0, 0]
        self.me["pos"] = [-40, 0, 0]
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "scheduled")
        self.advance(91)
        self.assertIsNotNone(self.choose())
        self.assertEqual(self.planner.state, "approach")

    def test_inside_unlanded_ring_does_not_force_early_idle(self):
        self.me["pos"] = list(self.drop["pos"])
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "scheduled")

    def test_server_holder_and_progress_control_remaining_capture_not_own_guess(self):
        self.me["pos"] = list(self.drop["pos"])
        self.advance(95)
        first = self.choose()
        self.assertTrue(first.holding)
        self.assertEqual(first.move, (0., 0.))
        self.assertAlmostEqual(first.capture_at, 99)
        self.advance(96.6)
        self.drop.update(holder=self.me["id"], progress=1.6)
        later = self.choose()
        self.assertAlmostEqual(later.capture_at, 99)
        self.assertTrue(later.holding)
        self.advance(97.6)
        self.assertIsNone(self.choose())
        self.assertIn("clock", self.planner.reason)

    def test_actual_drop_event_or_removed_object_ends_the_mission(self):
        self.assertIsNotNone(self.choose())
        self.advance(99)
        self.obs["events"] = [{"type": "drop", "id": 20000, "cubes": 3}]
        self.obs["drops"] = []
        self.assertIsNone(self.choose())
        self.assertIsNone(self.planner.drop_id)

    def test_committed_capture_can_finish_after_the_new_start_cutoff(self):
        self.assertIsNotNone(self.choose())
        self.advance(104)  # Nine seconds after landing; new starts are closed.
        self.me["pos"] = [200, 0, 0]
        self.drop.update(holder=self.me["id"], progress=3)
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertTrue(mission.holding)
        self.assertEqual(mission.capture_at, 105)

    def test_timed_travel_yields_to_held_laser_but_stationary_capture_can_use_it(self):
        self.me["weapons"][1] = {"kind": "laser", "charge": .5, "cooldown": 0,
                                   "stats": copy.deepcopy(self.config["weapons"]["laser"])}
        self.assertIsNone(self.choose())
        self.me["pos"] = [200, 0, 0]
        self.advance(95)
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertFalse(mission.gun_only)
        self.assertEqual(mission.move, (0., 0.))

    def test_foreign_holder_or_hostile_inside_ring_aborts_before_approach(self):
        self.drop["holder"] = 2
        self.assertIsNone(self.choose())
        self.drop["holder"] = None
        self.assertIsNone(self.choose([(self.enemy(201), 1)]))
        self.assertIn("contest", self.planner.reason)

    def test_final_capture_window_must_beat_a_real_hostile_arrival(self):
        self.me.update(pos=[200, 0, 0], hp=1400)
        self.advance(95)
        self.assertIsNone(self.choose([(self.enemy(300), 1)], recovering=False))
        self.assertIn("contest", self.planner.reason)

    def test_under_fire_repair_requires_surviving_before_the_refill(self):
        self.me["pos"] = [200, 0, 0]
        self.advance(95)
        hunter = self.enemy(400)
        self.assertIsNone(self.choose([(hunter, 1)]))
        self.assertIn("survive", self.planner.reason)
        self.advance(100)
        self.me["hp"] = 1400
        self.assertIsNotNone(self.choose([(hunter, 1)], recovering=False))

    def test_laser_burst_counts_two_full_beams_in_four_second_capture(self):
        self.me["pos"] = [200, 0, 0]
        self.advance(95)
        hunter = self.enemy(400)
        hunter["weapons"] = ["laser"]
        # Two315beams leave70HP, below the stated168HP escape reserve.
        self.assertIsNone(self.choose([(hunter, 1)]))

    def test_storm_checks_route_arrival_and_capture_end_not_just_drop_endpoint(self):
        self.obs["zone"].update(next_center=[-100, 0], next_radius=50, shrink_start=70, shrink_end=99)
        self.assertIsNone(self.choose())
        self.assertIn("zone", self.planner.reason)

    def test_inward_route_does_not_require_old_departure_point_in_final_circle(self):
        self.drop["pos"] = [0, 0, 0]
        self.obs["zone"].update(center=[-100, 0], radius=130, next_center=[0, 0],
                                next_radius=100, shrink_start=70, shrink_end=100)
        self.circle = ([0, 0], 100)
        self.advance(87)
        self.assertIsNotNone(self.choose())

    def test_growth_after_three_cubes_must_fit_the_selected_capture_point(self):
        wall = flat_world([rectangle(197, -25, 203, -2.8), rectangle(197, 2.8, 203, 25)])
        wall.bounds = self.world.bounds
        self.planner = TimedDrop(wall, self.config)
        self.assertTrue(wall.body_clear(200, 0, 0, 2.5, 9))
        self.assertIsNone(self.choose())

    def test_incomplete_or_wrong_side_grid_route_is_never_a_capture_route(self):
        wall = flat_world([rectangle(-2, -60, 2, 60)])
        wall.bounds = self.world.bounds
        self.planner = TimedDrop(wall, self.config)
        self.me["pos"] = [-20, 0, 0]
        goal = (5, 0, 0)
        self.planner.nav.search_done = True
        with patch.object(self.planner.nav, "plan", return_value=[(-3.5, 0, 0)]):
            self.assertIsNone(self.planner._route(self.me, goal, self.circle, []))
        self.planner.nav.search_done = False
        with patch.object(self.planner.nav, "plan", return_value=[(5, 0, 0)]):
            self.assertIsNone(self.planner._route(self.me, goal, self.circle, []))

    def test_independent_drop_search_does_not_replace_parent_navigator_state(self):
        parent = Navigator(self.world, self.config["mech"])
        parent.path = [(1, 2, 0)]
        parent.search = ("sentinel",)
        child = TimedDrop(self.world, self.config, parent)
        self.assertIs(child.nav.points, parent.points)
        self.assertIsNot(child.nav.path, parent.path)
        child.choose(self.obs, [], self.circle)
        self.assertEqual(parent.path, [(1, 2, 0)])
        self.assertEqual(parent.search, ("sentinel",))

    def test_completed_bent_route_is_reused_without_resuming_finished_astar(self):
        wall = flat_world([rectangle(-3, -25, 3, 25)])
        wall.bounds = self.world.bounds
        self.drop["pos"] = [100, 0, 0]
        self.planner = TimedDrop(wall, self.config)
        mission = None
        for i in range(20):
            self.advance(86+i*.3)
            mission = self.choose()
            if mission:
                break
        self.assertIsNotNone(mission)
        self.assertGreater(len(self.planner.cached_route), 3)
        self.advance(self.obs["t"]+.1)
        with patch.object(self.planner.nav, "plan", side_effect=AssertionError("completed A* resumed")):
            self.assertIsNotNone(self.choose())


def timed_capture(integrated=False):
    """Measured20Hz ground movement and actual ring clock for a free route.

    This isolates whether the route can arrive and hold; it does not model house
    AI or claim that the same drop will be unopposed in scored practice.
    """
    case = DropTests()
    case.setUp()
    m, obs, drop, planner = case.me, case.obs, case.drop, case.planner
    bot = None
    if integrated:
        bot = Bot(case.hello)
        bot.world, bot.nav, bot.drop = case.world, planner.nav, planner
        bot.motion = GroundSteering(case.world, case.config)
    progress, capture_time, minimum_energy = 0., None, m["energy"]
    action = None
    for tick in range(700):
        now = 70+tick*.05
        if tick % 2 == 0:
            obs.update(t=now, tick=1400+tick)
            drop.update(lands_in=max(0, 95-now), progress=progress,
                        holder=m["id"] if progress > 0 else None)
            if bot:
                action = bot.act(obs)
                if action["jump"]:
                    raise AssertionError("a ground supply route must not jump")
            else:
                action = planner.choose(obs, [], case.circle, recovering=True)
        if bot:
            move, sprint = action["move"], action["boost"]
        else:
            move = action.move if action and action.move is not None else unit(
                action.waypoint[0]-m["pos"][0], action.waypoint[1]-m["pos"][1]) if action else (0, 0)
            sprint = bool(action and action.sprint and m["energy"] > planner.RESERVE_ENERGY)
        speed = m["stats"]["boost_speed"] if sprint else m["stats"]["walk_speed"]
        dv = [move[i]*speed-m["vel"][i] for i in range(2)]
        scale = min(1, m["stats"]["ground_accel"]*.05/max(1e-9, math.hypot(*dv)))
        m["vel"] = [m["vel"][i]+dv[i]*scale for i in range(2)]+[0]
        m["pos"] = [m["pos"][i]+m["vel"][i]*.05 for i in range(2)]+[0]
        if sprint:
            m["energy"] -= m["stats"]["boost_drain"]*.05
        minimum_energy = min(minimum_energy, m["energy"])
        if now >= 95 and distance(m["pos"], drop["pos"]) < drop["radius"]:
            progress += .05
        else:
            progress = 0
        if progress >= 4-1e-8:
            capture_time = now+.05
            break
    return capture_time, minimum_energy, progress


class DropTimingTests(unittest.TestCase):
    def test_announced_three_hundred_meter_route_physically_arrives_and_holds(self):
        for integrated in (False, True):
            with self.subTest(integrated=integrated):
                at, energy, progress = timed_capture(integrated)
                self.assertIsNotNone(at)
                self.assertLessEqual(at, 100)
                self.assertGreaterEqual(progress, 4-1e-8)
                self.assertGreaterEqual(energy, 34)


if __name__ == "__main__":
    unittest.main()
