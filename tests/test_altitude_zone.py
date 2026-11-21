"""Phase-aware zone anchors preserve safe roof space without reusing launch checks."""
import copy
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.altitude import RoofSanctuary
from sentinel.geometry import distance


class AltitudeZoneTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.world = flat_world([rectangle(-30, -25, 30, 25, top=25)])
        self.roof = RoofSanctuary(self.world, self.hello["config"])
        self.site = self.roof.sites[0]
        self.me = self.obs["self"]
        self.me.update(pos=list(self.site["hold"]), hp=1400, energy=100,
                       vel=[0, 0, 0], grounded=True, in_zone=True)
        self.obs.update(t=20, tick=400, events=[], mechs=[], projectiles=[])
        self.obs["zone"].update(center=[0, 0], radius=118, next_center=[0, 0], next_radius=118,
                                shrink_start=500, shrink_end=550)
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "hold", float("inf")
        self.roof.hold_goal = tuple(self.site["hold"])

    def test_preflight_still_requires_launch_entry_and_hold_inside_circle(self):
        self.assertFalse(self.roof.safe_in_zone(self.site, ([0, 0], 25)))
        self.roof.cancel(0)
        self.roof.next_search = 0
        self.roof.sites = [self.site]
        self.me["pos"] = list(self.site["launch"])
        self.assertIsNone(self.roof.update(self.obs, [], ([0, 0], 25)))

    def test_inflight_ignores_launch_but_requires_viable_entry_and_roof(self):
        self.roof.phase, self.roof.deadline = "ascend", 28
        self.me.update(pos=[*self.site["launch"][:2], 5], grounded=False)
        self.roof.best_height, self.roof.last_rise = 5, 20
        control = self.roof.update(self.obs, [], ([0, 0], 25))
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "ascend")
        self.assertTrue(control["boost"])

    def test_safe_25_meter_roof_hold_does_not_depend_on_old_ground_launch(self):
        self.assertGreater(distance(self.site["launch"], [0, 0]), 25)
        control = self.roof.update(self.obs, [], ([0, 0], 25))
        self.assertEqual(self.roof.phase, "hold")
        self.assertEqual(control, {"move": [0, 0], "boost": False, "jump": False})

    def test_five_meter_circle_retargets_live_goal_without_mutating_site_cache(self):
        original = copy.deepcopy({key: value for key, value in self.site.items() if key != "prism"})
        cache = dict(self.roof.valid_cache)
        control = self.roof.update(self.obs, [], ([10, 0], 5))
        self.assertEqual(self.roof.phase, "settle")
        self.assertEqual(self.roof.hold_goal, (10, 0, 25))
        self.assertGreater(control["move"][0], 0)
        self.assertFalse(control["jump"])
        self.assertEqual(original, {key: value for key, value in self.site.items() if key != "prism"})
        self.assertEqual(self.roof.valid_cache, cache)

    def test_small_circle_margin_scales_instead_of_consuming_entire_circle(self):
        self.assertEqual(self.roof.zone_margin(([0, 0], 5)), 1)
        self.assertEqual(self.roof.zone_margin(([0, 0], 1)), .5)
        self.assertTrue(self.roof.point_in_zone([0, 0], ([0, 0], 1)))

    def test_circle_over_courtyard_hole_has_no_supported_same_roof_anchor(self):
        prism = rectangle(-30, -30, 30, 30, top=25,
                          holes=[[-10, -10, 10, -10, 10, 10, -10, 10]])
        self.world = flat_world([prism])
        self.roof = RoofSanctuary(self.world, self.hello["config"])
        self.site = self.roof.sites[0]
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "hold", float("inf")
        self.roof.hold_goal = tuple(self.site["hold"])
        self.me["pos"] = list(self.site["hold"])
        control = self.roof.update(self.obs, [], ([0, 0], 5))
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "exit")

    def test_another_nearby_roof_is_not_a_same_roof_anchor(self):
        self.world = flat_world([rectangle(-30, -25, 30, 25, top=25),
                                 rectangle(50, -25, 90, 25, top=25)])
        self.roof = RoofSanctuary(self.world, self.hello["config"])
        self.site = next(site for site in self.roof.sites if site["prism"].contains(0, 0))
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "hold", float("inf")
        self.me["pos"] = list(self.site["hold"])
        control = self.roof.update(self.obs, [], ([65, 0], 5))
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "exit")

    def test_no_new_excursion_outside_observed_current_zone_for_roof_retarget(self):
        # Deliberately inconsistent future data must not justify walking through
        # the current storm. Real nested circles satisfy this by construction.
        self.obs["zone"].update(center=[0, 0], radius=5)
        control = self.roof.update(self.obs, [], ([10, 0], 5))
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "exit")


if __name__ == "__main__":
    unittest.main()
