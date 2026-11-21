"""Roof geometry, early eligibility, live dimensions, and bounded search guards."""
import copy
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.altitude import RoofSanctuary


class AltitudeCoreTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.world = flat_world([rectangle(-30, -25, 30, 25, top=25)])
        self.roof = RoofSanctuary(self.world, self.hello["config"])
        self.site = self.roof.sites[0]
        self.me = self.obs["self"]
        self.me.update(pos=list(self.site["launch"]), hp=1400, energy=100,
                       vel=[0, 0, 0], grounded=True, in_zone=True)
        self.obs.update(t=20, tick=400, events=[], mechs=[], projectiles=[])
        self.circle = ([0, 0], 110)

    def test_entry_and_hold_are_supported_with_deep_body_inset(self):
        self.assertTrue(self.roof.sites)
        for site in self.roof.sites:
            self.assertFalse(site["prism"].contains(*site["launch"][:2]))
            self.assertTrue(self.roof.supported(site["prism"], site["landing"], 3))
            self.assertTrue(self.roof.supported(site["prism"], site["hold"], 5))
            self.assertTrue(self.roof.roof_path(site["prism"], site["landing"], site["hold"], 3, 9))

    def test_overhead_slab_blocks_whole_body_launch_columns(self):
        world = flat_world([rectangle(-30, -25, 30, 25, top=25),
                            rectangle(-100, -100, 100, 100, base=11, top=12)])
        self.assertEqual(RoofSanctuary(world, self.hello["config"]).sites, [])

    def test_courtyard_hole_is_not_a_walkable_roof_corridor(self):
        prism = rectangle(-30, -30, 30, 30, top=25,
                          holes=[[-10, -10, 10, -10, 10, 10, -10, 10]])
        world = flat_world([prism])
        roof = RoofSanctuary(world, self.hello["config"])
        self.assertFalse(roof.roof_path(prism, (-20, 0), (20, 0), 3, 9))
        self.assertFalse(roof.supported(prism, (0, 0), 3))

    def test_growth_revalidates_cached_site_with_new_body(self):
        self.assertTrue(self.roof.valid_site(self.site, self.me))
        self.me["stats"]["radius"] = 9
        self.assertFalse(self.roof.valid_site(self.site, self.me))

    def test_arrival_error_does_not_jet_under_the_planned_roof_eave(self):
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "approach", 32
        launch, entry = self.site["launch"], self.site["landing"]
        direction = [(entry[i]-launch[i])/(sum((entry[j]-launch[j])**2 for j in range(2))**.5)
                     for i in range(2)]
        self.me["pos"] = [launch[i]+direction[i]*2.4 for i in range(2)]+[launch[2]]
        control = self.roof.update(self.obs, [], self.circle)
        self.assertFalse(control.get("jump", False))
        self.assertFalse(control.get("boost", False))
        self.assertEqual(self.roof.phase, "approach")

    def test_new_weapon_hit_cancels_unstarted_approach(self):
        self.me["pos"][0] -= 8
        self.assertIsNotNone(self.roof.update(self.obs, [], self.circle))
        self.obs.update(t=20.1, events=[{"type": "damaged", "weapon": "gun", "amount": 45}])
        self.assertIsNone(self.roof.update(self.obs, [], self.circle))
        self.assertIsNone(self.roof.site)

    def test_failed_launch_is_temporarily_skipped(self):
        self.roof.site, self.roof.phase = self.site, "approach"
        self.roof.cancel(20, True, "blocked launch")
        self.assertGreater(self.roof.failed[id(self.site)], 20)
        self.roof.sites = [self.site]
        self.assertIsNone(self.roof.choose(self.obs, [], self.circle))

    def test_live_growth_on_wide_held_roof_ignores_obsolete_narrow_entry(self):
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "hold", float("inf")
        self.me["pos"] = list(self.site["hold"])
        self.me["stats"]["radius"] = 9
        control = self.roof.update(self.obs, [], self.circle)
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "hold")
        self.assertFalse(self.roof.valid_site(self.site, self.me))
        self.assertTrue(self.roof.supported(self.site["prism"], self.me["pos"], 9.3))
        self.assertIsNotNone(self.roof.site)

    def test_body_that_no_longer_fits_actual_held_roof_keeps_exit_ownership(self):
        self.roof.site, self.roof.phase, self.roof.deadline = self.site, "hold", float("inf")
        self.me["pos"] = list(self.site["hold"])
        self.me["stats"]["radius"] = 29
        control = self.roof.update(self.obs, [], self.circle)
        self.assertIsNotNone(control)
        self.assertEqual(self.roof.phase, "exit")
        self.assertIsNotNone(self.roof.site)


if __name__ == "__main__":
    unittest.main()
