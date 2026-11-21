"""A real hit has time to bring an unseen shooter into the torso's view."""
import unittest

from sentinel.strategy import Bot
from sentinel.combat import Combat
from sentinel.navigation import Navigator
from test_bot import fixture, flat_world


class IncomingBearingTests(unittest.TestCase):
    def setUp(self):
        hello, self.obs = fixture()
        self.obs.update(t=100, tick=2000, alive=13, mechs=[], projectiles=[],
                        crates=[], pickups=[], cubes=[], drops=[], sounds=[])
        self.bot = Bot(hello)
        self.bearing = 2.412

    def hint(self, *, by=1, weapon="gun"):
        self.obs["events"] = [dict(type="damaged", amount=45, bearing=self.bearing,
                                   weapon=weapon, by=by)]
        self.assertEqual(self.bot.act(self.obs)["aim"][0], self.bearing)

    def step(self, seconds, events=()):
        self.obs.update(t=100+seconds, tick=round((100+seconds)*20), events=list(events))
        return self.bot.act(self.obs)

    def test_keeps_facing_across_observations_without_another_damage_event(self):
        self.hint()
        for age in (.1, .45, .8, 1.05):
            self.assertEqual(self.step(age)["aim"][0], self.bearing)
        self.assertNotEqual(self.step(1.11)["aim"][0], self.bearing)

    def test_npc_damage_and_confirmed_elimination_do_not_leave_a_persistent_hint(self):
        self.hint(by=100, weapon="npc")
        self.assertNotEqual(self.step(.1)["aim"][0], self.bearing)
        self.hint()
        action = self.step(.2, [dict(type="kill", target=1)])
        self.assertNotEqual(action["aim"][0], self.bearing)

    def test_current_combat_aim_has_priority_over_a_stale_bearing(self):
        self.hint(by=2)
        world = flat_world()
        self.bot.world = world
        self.bot.nav = Navigator(world, self.bot.config["mech"])
        self.bot.combat = Combat(world, self.bot.config)
        self.obs["self"].update(pos=[0, 0, 0], vel=[0, 0, 0], hp=1400,
                                max_hp=1400, aim=[0, 0])
        self.obs["mechs"] = [dict(id=1, kind="mech", pos=[45, 0, 0], vel=[0, 0, 0],
                                  aim=[3.14, 0], hp=1000, max_hp=1400, weapons=["gun"])]
        self.obs["zone"].update(center=[0, 0], next_center=[0, 0], radius=120, next_radius=120)
        self.assertAlmostEqual(self.step(.2)["aim"][0], 0, places=5)


if __name__ == "__main__":
    unittest.main()
