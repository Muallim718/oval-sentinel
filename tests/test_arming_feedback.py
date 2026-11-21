"""Coupled cover/arming feedback on a flat protected corridor.

This independent 20 Hz movement and regeneration model is deliberately limited;
it does not reproduce the server, combat, or scored placement.
"""
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.provisioning import Provisioner
from sentinel.strategy import Bot


class ArmingFeedbackTests(unittest.TestCase):
    def test_recovering_bot_walks_protected_corridor_and_takes_laser(self):
        hello, obs = fixture()
        world = flat_world([rectangle(-2, -50, 2, 50)])
        bot = Bot(hello)
        bot.world = world
        bot.nav = Navigator(world, hello["config"]["mech"])
        bot.combat = Combat(world, hello["config"])
        bot.cover = CoverPlanner(world, hello["config"])
        bot.motion = GroundSteering(world, hello["config"])
        bot.provision = Provisioner(world, hello["config"])
        me = obs["self"]
        me.update(pos=[-8, -10, 0], vel=[0, 0, 0], aim=[math.pi/2, 0],
                  hp=700, energy=100, grounded=True, in_zone=True)
        obs.update(t=0, tick=0, alive=16, events=[], projectiles=[], cubes=[],
                   crates=[], drops=[], offer=None)
        obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0],
                            next_radius=118, shrink_start=500, shrink_end=550)
        # The tracked enemy remains on the other side of this solid wall. The
        # known laser is 20.4 m along the same protected, walkable side.
        enemy = {"id": 1, "kind": "mech", "pos": [35, 0, 0],
                 "vel": [0, 0, 0], "aim": [math.pi, 0], "hp": 1400,
                 "max_hp": 1400, "weapons": ["gun", "laser"]}
        laser = {"id": 8001, "kind": "laser", "pos": [-8, 10.4, 0]}
        obs["mechs"], obs["pickups"] = [enemy], [laser]
        stats = me["stats"]
        last_spend = -100
        # Recovery is already eligible: no damage was dealt or taken for 5 s.
        quiet_since = -stats["regen_delay"]
        collected_at = None
        commands_that_moved = 0
        initial_position = list(me["pos"])

        for decision in range(80):
            obs.update(t=decision*.1, tick=decision*2, events=[])
            action = bot.act(obs)
            self.assertEqual(action["fire"], [False, False])
            self.assertEqual(bot.mode, "recover")
            self.assertFalse(action["jump"])
            if math.hypot(*action["move"]) > .1:
                commands_that_moved += 1
            if action.get("take") == laser["id"]:
                pickup_distance = math.dist(me["pos"][:2], laser["pos"][:2])
                self.assertLessEqual(pickup_distance, 3.5)
                self.assertLessEqual(pickup_distance, hello["config"]["loot"]["pickup_radius"])
                self.assertLessEqual(abs(me["pos"][2]-laser["pos"][2]), 4)
                collected_at = obs["t"]
                break  # Accept the valid take; secondary combat is not modeled.

            speed = stats["boost_speed"] if action["boost"] else stats["walk_speed"]
            for substep in range(2):
                now = decision*.1+(substep+1)*.05
                moving = math.hypot(*action["move"]) > 0
                if action["boost"] and moving:
                    me["energy"] = max(0, me["energy"]-stats["boost_drain"]*.05)
                    last_spend = now
                elif now-last_spend >= stats["energy_regen_delay"]:
                    me["energy"] = min(me["max_energy"],
                                         me["energy"]+stats["energy_regen"]*.05)
                dx = action["move"][0]*speed-me["vel"][0]
                dy = action["move"][1]*speed-me["vel"][1]
                amount = math.hypot(dx, dy)
                fraction = min(1, stats["ground_accel"]*.05/amount) if amount else 0
                vx, vy = me["vel"][0]+dx*fraction, me["vel"][1]+dy*fraction
                proposed = [me["pos"][0]+vx*.05, me["pos"][1]+vy*.05, 0]
                self.assertTrue(world.walk_clear(me["pos"], proposed, stats["radius"],
                                                stats["height"], stats["step_up"],
                                                stats["max_slope_deg"]))
                me["pos"], me["vel"] = proposed, [vx, vy, 0]
                # Check both center heights every physics step. The wall extends
                # well beyond the entire route, so lateral flanks remain covered.
                for height in (.5, .95):
                    self.assertFalse(world.line_clear([35, 0, 7],
                        [*me["pos"][:2], me["pos"][2]+stats["height"]*height]))
                if now-quiet_since >= stats["regen_delay"]:
                    me["hp"] = min(me["max_hp"], me["hp"]+stats["regen_per_s"]*.05)

        self.assertIsNotNone(collected_at, "cover holding prevented physical weapon collection")
        self.assertLess(collected_at, 8)
        self.assertGreater(commands_that_moved, 3)
        self.assertGreater(math.dist(initial_position, me["pos"]), 15)
        self.assertGreater(me["hp"], 700)


if __name__ == "__main__":
    unittest.main()
