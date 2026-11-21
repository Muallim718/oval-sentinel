"""Ground control with an independent 20 Hz acceleration/energy feedback model.

This is a limited local model, not the authoritative server or a placement test.
"""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.provisioning import Provisioner
from sentinel.navigation import Navigator
from sentinel.strategy import Bot


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-6, 18, 0], vel=[0, 0, 0], hp=700, energy=100,
                       grounded=True)
        self.obs.update(t=0, tick=0, events=[], projectiles=[], mechs=[],
                        crates=[], cubes=[], pickups=[], drops=[])
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                                next_radius=118, shrink_start=500, shrink_end=550)
        self.world = flat_world([rectangle(0, -20, 5, 20)])
        self.control = GroundSteering(self.world, self.hello["config"])
        self.enemy = {"id": 1, "kind": "mech", "pos": [35, 0, 0],
                      "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                      "max_hp": 1400, "weapons": ["gun"]}
        self.last_spend = -100

    def body_visible(self):
        return self.lane_visible_at(self.me["pos"])

    def lane_visible_at(self, position):
        # Independent ray oracle: do not use GroundSteering.exposed(). Include
        # lateral head samples so a corner cannot hide a grazing body flank.
        start = [35, 0, 7]
        dx, dy = position[0]-35, position[1]
        length = math.hypot(dx, dy)
        side_x = -dy/length*self.me["stats"]["radius"]*.95
        side_y = dx/length*self.me["stats"]["radius"]*.95
        top = position[2]+self.me["stats"]["height"]*.95
        points = [[*position[:2], position[2]+self.me["stats"]["height"]*.5],
                  [*position[:2], top],
                  [position[0]+side_x, position[1]+side_y, top],
                  [position[0]-side_x, position[1]-side_y, top]]
        return any(self.world.line_clear(start, point) for point in points)

    def feedback(self, move, sprinting, decision):
        """Two 0.05 s ground steps, separate from the controller's forecast."""
        stats = self.me["stats"]
        speed = stats["boost_speed"] if sprinting else stats["walk_speed"]
        positions = []
        for tick in range(2):
            now = decision*.1+tick*.05
            if sprinting and math.hypot(*move) > 0:
                self.me["energy"] = max(0, self.me["energy"]-
                                          stats["boost_drain"]*.05)
                self.last_spend = now
            elif now-self.last_spend >= stats["energy_regen_delay"]:
                self.me["energy"] = min(self.me["max_energy"],
                                          self.me["energy"]+stats["energy_regen"]*.05)
            target_x, target_y = move[0]*speed, move[1]*speed
            dx = target_x-self.me["vel"][0]
            dy = target_y-self.me["vel"][1]
            amount = math.hypot(dx, dy)
            fraction = min(1, stats["ground_accel"]*.05/amount) if amount else 0
            vx = self.me["vel"][0]+dx*fraction
            vy = self.me["vel"][1]+dy*fraction
            proposed = [self.me["pos"][0]+vx*.05,
                        self.me["pos"][1]+vy*.05, self.me["pos"][2]]
            if self.world.walk_clear(self.me["pos"], proposed,
                                     stats["radius"], stats["height"], stats["step_up"]):
                self.me["pos"], self.me["vel"] = proposed, [vx, vy, 0]
            else:
                # Deliberately conservative collision; this model does not
                # duplicate the server's axis sliding or ledge rules.
                self.me["vel"] = [0, 0, 0]
            positions.append(list(self.me["pos"]))
        return positions

    def choose(self, goal, threats=None, sprinting=False, cover=True):
        if threats is None:
            threats = [(self.enemy, 1)]
        return self.control.choose(self.obs, goal, threats, "recover", 65, True,
                                   sprinting=sprinting, cover=cover,
                                   circle=([0, 0], 118))

    def integrated_bot(self):
        bot = Bot(self.hello)
        bot.world = self.world
        bot.nav = Navigator(self.world, self.hello["config"]["mech"])
        bot.combat = Combat(self.world, self.hello["config"])
        bot.cover = CoverPlanner(self.world, self.hello["config"])
        bot.provision = Provisioner(self.world, self.hello["config"])
        bot.motion = GroundSteering(self.world, self.hello["config"])
        self.obs["mechs"] = [self.enemy]
        return bot

    def test_low_wall_does_not_hide_exposed_head(self):
        self.world = flat_world([rectangle(0, -20, 5, 20, top=8)])
        self.control = GroundSteering(self.world, self.hello["config"])
        self.me["pos"] = [-6, 0, 0]
        self.assertFalse(self.world.line_clear([35, 0, 7], [-6, 0, 5.85]))
        self.assertTrue(self.world.line_clear([35, 0, 7], [-6, 0, 8.55]))
        self.assertTrue(self.control.exposed(self.me["pos"], self.me, self.enemy))

    def test_sheltered_fixed_waypoint_holds_for_ten_seconds(self):
        goal = tuple(self.me["pos"][:2])
        self.assertFalse(self.body_visible())
        stopped = 0
        for decision in range(100):
            self.obs.update(t=decision*.1, tick=decision*2)
            move, sprinting = self.choose(goal, sprinting=True)
            stopped += math.hypot(*move) < 1e-8
            self.feedback(move, sprinting, decision)
            self.assertFalse(self.body_visible())
            self.assertLess(math.dist(self.me["pos"][:2], goal), .25)
        self.assertEqual(stopped, 100)
        self.assertGreaterEqual(self.me["energy"], 99)

    def test_fast_corner_approach_turns_or_brakes_without_opening_firing_lane(self):
        self.me.update(pos=[-6, 19, 0], vel=[0, 19.5, 0])
        goal = (-6, 14)
        self.assertFalse(self.body_visible())
        first_move = None
        for decision in range(25):
            self.obs.update(t=decision*.1, tick=decision*2)
            move, sprinting = self.choose(goal, sprinting=True)
            if first_move is None:
                first_move = move
            # Check every physics step, not just every observation endpoint.
            for position in self.feedback(move, sprinting, decision):
                self.assertFalse(self.lane_visible_at(position),
                                 f"exposed at {position}")
        self.assertLess(first_move[1], .8)
        self.assertLess(math.dist(self.me["pos"][:2], goal), 5)

    def test_incoming_projectile_causes_lateral_dodge(self):
        self.world = flat_world()
        self.control = GroundSteering(self.world, self.hello["config"])
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0])
        self.obs["projectiles"] = [{"id": 2001, "kind": "gun",
                                     "pos": [40, 0, 7], "vel": [-80, 0, 0]}]
        move, sprinting = self.choose((80, 0), threats=[], cover=False)
        self.assertGreater(abs(move[1]), .4)
        minimum = math.inf
        # Hold the chosen command for 0.5 s and sample the relative bullet path.
        for decision in range(5):
            for tick, position in enumerate(self.feedback(move, sprinting, decision)):
                elapsed = decision*.1+(tick+1)*.05
                bullet_x = 40-80*elapsed
                minimum = min(minimum, math.hypot(position[0]-bullet_x, position[1]))
        self.assertGreater(minimum, self.me["stats"]["radius"]+1)

    def test_clear_waypoint_progresses_without_freezing(self):
        self.world = flat_world()
        self.control = GroundSteering(self.world, self.hello["config"])
        self.me.update(pos=[-60, 0, 0], vel=[0, 0, 0])
        for decision in range(50):
            self.obs.update(t=decision*.1, tick=decision*2)
            move, sprinting = self.choose((60, 0), threats=[], cover=False)
            self.assertGreater(math.hypot(*move), .5)
            self.feedback(move, sprinting, decision)
        self.assertGreater(self.me["pos"][0], -10)
        self.assertLess(abs(self.me["pos"][1]), 3)

    def test_sheltered_recovering_bot_does_not_lob_mortar_at_weak_target(self):
        # This wall protects the body, while the head-mounted mortar's arc can
        # clear its top. Without healing suppression a weak-target exception fires.
        self.world = flat_world([rectangle(0, -20, 1, 20, top=9)])
        bot = self.integrated_bot()
        self.enemy["hp"] = 120
        mortar = {"kind": "mortar", "cooldown": 0,
                  "stats": copy.deepcopy(self.hello["config"]["weapons"]["mortar"])}
        self.me["weapons"][1] = mortar
        solution = bot.combat.solve(self.me, self.enemy, mortar)
        self.assertIsNotNone(solution, "scenario must offer an over-wall shot")
        self.me["aim"] = solution[0]
        action = bot.act(self.obs)
        self.assertEqual(bot.mode, "recover")
        self.assertIsNone(bot.duel)
        self.assertTrue(bot.cover.sheltered)
        self.assertEqual(action["fire"], [False, False])
        self.assertLess(math.hypot(*action["move"]), 1e-8)

    def test_existing_escape_jet_is_canceled_when_safely_holding(self):
        bot = self.integrated_bot()
        bot.jet_until = self.obs["t"]+4
        bot.jet_started_z = 0
        action = bot.act(self.obs)
        self.assertTrue(bot.cover.sheltered)
        self.assertFalse(action["jump"])
        self.assertFalse(action["boost"])
        self.assertLess(math.hypot(*action["move"]), 1e-8)

    def test_weak_target_does_not_interrupt_partially_completed_recovery(self):
        bot = self.integrated_bot()
        bot.act(self.obs)  # Start recovery below the threshold.
        self.me["hp"] = 1000
        self.enemy["hp"] = 120
        self.obs.update(t=.1, tick=2)
        action = bot.act(self.obs)
        self.assertTrue(bot.recovering)
        self.assertEqual(bot.mode, "recover")
        self.assertIsNone(bot.duel)
        self.assertEqual(action["fire"], [False, False])
        self.assertLess(math.hypot(*action["move"]), 1e-8)

    def test_enemy_flank_releases_previous_hold_immediately(self):
        bot = self.integrated_bot()
        bot.act(self.obs)
        old_goal = bot.goal
        self.enemy["pos"] = [-25, 30, 0]
        self.obs.update(t=.1, tick=2)
        action = bot.act(self.obs)
        self.assertFalse(bot.cover.sheltered)
        self.assertNotEqual(bot.goal, old_goal)
        self.assertGreater(math.hypot(*action["move"]), .5)

    def test_new_zone_releases_previous_hold_for_an_inside_destination(self):
        bot = self.integrated_bot()
        bot.act(self.obs)
        old_goal = bot.goal
        self.obs["zone"].update(center=[40, 0], radius=30, next_center=[40, 0],
                                next_radius=30, shrink_start=500, shrink_end=550)
        self.me["in_zone"] = False
        self.obs.update(t=.1, tick=2)
        action = bot.act(self.obs)
        self.assertFalse(bot.cover.sheltered)
        self.assertNotEqual(bot.goal, old_goal)
        self.assertLess(math.dist(bot.goal, [40, 0]), 30)
        self.assertGreater(math.hypot(*action["move"]), .5)

    def test_partial_route_dead_end_eventually_abandons_distant_cover(self):
        self.me["pos"] = [-8, 36, 0]
        bot = self.integrated_bot()
        # Fault-inject an exhausted/partial navigator: its best reachable point
        # remains half a meter away. The old >8 m waypoint stuck check cannot
        # detect the distant destination making no progress. Observations stay
        # fixed to represent a mech physically unable to leave this pocket.
        bot.nav.waypoint = lambda *args: [-7.5, 36, 0]
        bot.act(self.obs)
        goal = bot.goal
        self.assertTrue(bot.cover_active)
        self.assertGreater(math.dist(self.me["pos"][:2], goal), 4)
        abandoned = False
        for decision in range(1, 51):
            self.obs.update(t=decision*.1, tick=decision*2)
            action = bot.act(self.obs)
            self.assertFalse(action["jump"])
            if bot.goal != goal:
                abandoned = True
            if abandoned:
                self.assertNotEqual(bot.goal, goal)
        self.assertTrue(abandoned, "unreachable refuge commitment was never released")

    def test_exposed_healthy_duel_keeps_moving_at_ideal_range(self):
        self.world = flat_world()
        self.control = GroundSteering(self.world, self.hello["config"])
        self.me.update(pos=[-30, 0, 0], vel=[0, 0, 0], hp=1400)
        for decision in range(30):
            self.obs.update(t=decision*.1, tick=decision*2)
            move, sprinting = self.control.choose(
                self.obs, (-30, 0), [(self.enemy, 1)], "fight", 65, False,
                sprinting=False, cover=False, circle=([0, 0], 118))
            self.assertGreater(math.hypot(*move), .5)
            self.feedback(move, sprinting, decision)
        self.assertGreater(math.dist(self.me["pos"], self.enemy["pos"]), 40)
        self.assertLess(math.dist(self.me["pos"], self.enemy["pos"]), 90)


if __name__ == "__main__":
    unittest.main()
