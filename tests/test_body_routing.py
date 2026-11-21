"""The body-size-only ablation: retain revision 2 behavior outside navigation."""
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.navigation import Navigator
from sentinel.strategy import Bot


class BodyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.hello,self.obs = fixture()

    def test_same_body_preserves_routes_and_search(self):
        nav = Navigator(flat_world(),self.hello["config"]["mech"])
        nav.path = [(0,0,0)]
        search = object()
        nav.search = search
        nav.set_body(self.obs["self"]["stats"])
        self.assertEqual(nav.path,[(0,0,0)])
        self.assertIs(nav.search,search)
        self.assertFalse(nav.body_changed)

    def test_growth_invalidates_cached_passage_and_search(self):
        world = flat_world([rectangle(-30,-80,30,-5.5),rectangle(-30,5.5,30,80)])
        nav = Navigator(world,self.hello["config"]["mech"])
        k = nav.nearest((0,0))
        self.assertTrue(nav.valid_at(k))
        self.assertTrue(nav.neighbors(k))
        nav.path = [nav.points[k]]
        nav.search = object()
        nav.set_body({"radius":6,"height":21.6})
        self.assertFalse(nav.valid_at(k))
        self.assertEqual(nav.neighbors(k),[])
        self.assertEqual(nav.path,[])
        self.assertIsNone(nav.search)
        self.assertTrue(nav.search_done)

    def test_height_growth_rejects_low_bridge(self):
        world = flat_world([rectangle(-30,-30,30,30,base=11,top=13)])
        nav = Navigator(world,self.hello["config"]["mech"])
        k = nav.nearest((0,0))
        self.assertTrue(nav.valid_at(k))
        nav.set_body({"radius":3.5,"height":12.6})
        self.assertFalse(nav.valid_at(k))

    def test_enlarged_route_goes_around_impassable_gap(self):
        world = flat_world([rectangle(-25,-75,25,-5.5),rectangle(-25,5.5,25,75)])
        nav = Navigator(world,self.hello["config"]["mech"])
        nav.set_body({"radius":6,"height":21.6})
        for _ in range(150):
            path = nav.plan((-65,0,0),(65,0),((0,0),200))
            if nav.search_done:
                break
        self.assertTrue(nav.search_done)
        self.assertTrue(path)
        self.assertLess(abs(path[-1][0]-65),9)
        self.assertGreater(max(abs(p[1]) for p in path),80)
        for a,b in zip([(-65,0,0)]+path,path):
            self.assertTrue(world.walk_clear(a,b,radius=6.4,height=21.6))

    def test_next_cube_rechecks_previously_cached_clearance(self):
        nav = Navigator(flat_world([rectangle(0,-20,20,20)]),self.hello["config"]["mech"])
        k = nav.nearest((-6,0))
        nav.set_body({"radius":3,"height":10.8})
        nav.valid_at(k)
        self.assertIn(k,nav.clearance)
        nav.set_body({"radius":4,"height":14.4})
        self.assertEqual(nav.clearance,{})

    def test_bot_passes_live_upgraded_dimensions_to_navigator(self):
        bot = Bot(self.hello)
        self.obs["self"]["cubes"] = 6
        self.obs["self"]["stats"].update(radius=3.25,height=11.7)
        bot.act(self.obs)
        self.assertAlmostEqual(bot.nav.radius,3.65)
        self.assertAlmostEqual(bot.nav.height,11.7)


if __name__ == "__main__":
    unittest.main()
