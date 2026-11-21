"""Incoming-fire regressions with visible rounds and game-clock movement."""

import unittest

from sentinel.incoming import impact_cost, incoming_tracks
from sentinel.movement import forecast_path
from test_bot import fixture, flat_world, rectangle


class IncomingFireTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.config = hello["config"]
        self.me = self.obs["self"]
        self.me.update(pos=[0, 0, 0], vel=[0, 11.7, 0], grounded=True)
        self.world = flat_world()

    def bullet(self, position, velocity):
        return {"kind": "gun", "pos": position, "vel": velocity}

    def cost(self, command, world=None):
        speed = self.me["stats"]["walk_speed"]
        tracks = incoming_tracks(self.obs, self.config, speed)
        path = forecast_path(self.me, command, speed)
        return impact_cost(world or self.world, self.me, path, tracks, splash=7)

    def test_reversal_evades_a_lead_shot_that_intercepts_strafe(self):
        # A shot from 91 m reaches x=0 after .36 s, at the current strafe's y.
        self.obs["projectiles"] = [self.bullet([91, 4.22, 7], [-252, 0, 0])]
        self.assertGreater(self.cost((0, 1)), 30)
        self.assertEqual(self.cost((0, -1)), 0)

    def test_solid_wall_absorbs_a_round_before_predicted_impact(self):
        self.obs["projectiles"] = [self.bullet([83, 3.85, 7], [-252, 0, 0])]
        wall = flat_world([rectangle(40, -7, 41, 7, top=12)])
        self.assertEqual(self.cost((0, 1), wall), 0)

    def test_nearby_outbound_rounds_do_not_displace_incoming_track(self):
        inbound = self.bullet([83, 3.85, 7], [-252, 0, 0])
        self.obs["projectiles"] = [self.bullet([10+i, 0, 7], [252, 0, 0])
                                   for i in range(20)] + [inbound]
        tracks = incoming_tracks(self.obs, self.config, self.me["stats"]["walk_speed"])
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0][0], inbound["pos"])

    def test_round_clearing_the_head_is_not_a_collision(self):
        self.obs["projectiles"] = [self.bullet([83, 3.85, 10.5], [-252, 0, 0])]
        self.assertEqual(self.cost((0, 1)), 0)


if __name__ == "__main__":
    unittest.main()
