"""Body-aware routes, matchup selection, and roof flight feedback regressions.

The feedback model implements published acceleration, gravity, and energy rates
on simple test solids. It is not the authoritative match simulation.
"""
import copy
import math
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat, sustained_dps
from sentinel.elevation import RoofEscape
from sentinel.navigation import Navigator
from sentinel.geometry import World
from sentinel.strategy import Bot


class BodyAndMatchupTests(unittest.TestCase):
    def test_route_clearance_changes_when_cube_size_changes(self):
        w = flat_world([rectangle(-30,-110,30,-5.5),rectangle(-30,5.5,30,110)])
        h,o = fixture()
        nav = Navigator(w,h["config"]["mech"])
        k = nav.nearest([0,0,0])
        self.assertTrue(nav.valid_at(k))
        self.assertTrue(nav.neighbors(k))
        grown = {**o["self"]["stats"],"radius":6,"height":15}
        nav.set_body(grown)
        self.assertFalse(nav.valid_at(k))
        self.assertEqual(nav.neighbors(k),[])
        self.assertEqual(nav.path,[])

    def test_equal_health_does_not_make_gun_vs_gun_laser_favorable(self):
        h,o = fixture()
        bot = Bot(h)
        bot.world = flat_world()
        o["self"]["pos"] = [-60,0,0]
        enemy = {"kind":"mech","id":1,"pos":[0,0,0],"vel":[0,0,0],
                 "hp":1400,"max_hp":1400,"weapons":["gun","laser"]}
        o["mechs"] = [enemy]
        bot.select_mode(o)
        self.assertEqual(bot.mode,"evade")
        enemy["weapons"] = ["gun"]
        bot.select_mode(o)
        self.assertEqual(bot.mode,"fight")
        enemy["cubes"] = 8
        bot.select_mode(o)
        self.assertEqual(bot.mode,"evade")

    def test_matchup_respects_range_and_laser_cookoff(self):
        h,o = fixture()
        c = h["config"]
        near = sustained_dps(["gun","lightning"],c,0,30)
        far = sustained_dps(["gun","lightning"],c,0,80)
        self.assertGreater(near,far*2)
        a = sustained_dps(["laser"],c,0,90,[])
        b = sustained_dps(["laser"],c,0,90,["mortar"])
        self.assertGreater(b,a*1.5)


class RoofTests(unittest.TestCase):
    def setUp(self):
        self.h,self.o = fixture()
        self.w = flat_world([rectangle(-20,-20,20,20,top=20)])
        self.escape = RoofEscape(self.w,self.h["config"]["mech"])
        self.site = self.escape.sites[0]
        self.o["self"].update(pos=list(self.site["launch"]),vel=[0,0,0],hp=600)
        self.circle = ([0,0],110)

    def test_reachable_roof_has_launch_outside_and_landing_inside(self):
        site = self.escape.choose(self.o,[],self.circle)
        self.assertIsNotNone(site)
        self.assertFalse(site["prism"].contains(*site["launch"][:2]))
        self.assertTrue(site["prism"].contains(*site["landing"][:2]))

    def test_insufficient_energy_does_not_start_flight(self):
        self.o["self"]["energy"] = 30
        self.assertIsNone(self.escape.update(self.o,[],self.circle,True))

    def test_incoming_zone_invalidates_a_refuge(self):
        self.assertIsNotNone(self.escape.update(self.o,[],self.circle,True))
        self.o["t"] = 1
        self.assertIsNone(self.escape.update(self.o,[],([90,90],10),True))
        self.assertIsNone(self.escape.site)

    def test_overhead_bridge_blocks_jet_columns(self):
        ceiling = rectangle(-100,-100,100,100,base=11,top=12)
        ceiling.kind = "bridge"
        world = flat_world([rectangle(-20,-20,20,20,top=20),ceiling])
        escape = RoofEscape(world,self.h["config"]["mech"])
        self.assertEqual(escape.sites,[])

    def test_occupied_roofs_are_rejected(self):
        enemy = {"pos":[0,0,20]}
        self.assertIsNone(self.escape.choose(self.o,[(enemy,1)],self.circle))

    def test_growth_rechecks_launch_column_before_start(self):
        self.o["self"]["stats"]["radius"] = 9
        self.assertIsNone(self.escape.choose(self.o,[],self.circle))

    def test_vertical_progress_timeout_abandons_a_blocked_jet(self):
        self.escape.update(self.o,[],self.circle,True)
        self.o.update(t=2,tick=40)
        self.o["self"]["grounded"] = False
        self.assertIsNone(self.escape.update(self.o,[],self.circle,True))
        self.assertIsNone(self.escape.site)

    def flight_feedback(self,top,world=None,site_index=0):
        world = world or flat_world([rectangle(-20,-20,20,20,top=top)])
        escape = RoofEscape(world,self.h["config"]["mech"])
        obs = copy.deepcopy(self.o)
        me,s = obs["self"],obs["self"]["stats"]
        selected = escape.sites[site_index]
        escape.site,escape.phase,escape.deadline = selected,"approach",12
        me.update(pos=list(selected["launch"]),vel=[0,0,0],energy=100,grounded=True)
        circle = ([*selected["launch"][:2]],110)
        last_spent = -100
        phases = set()
        for decision in range(150):
            obs.update(t=decision*.1,tick=decision*2)
            controls = escape.update(obs,[],circle,True)
            if escape.phase:
                phases.add(escape.phase)
            if escape.phase == "rest":
                return me,phases
            self.assertIsNotNone(controls,f"controller abandoned flight at {me['pos']}")
            self.assertNotIn("approach",controls)
            for substep in range(2):
                now = obs["t"]+substep*.05
                if controls["jump"] and me["grounded"]:
                    me["vel"][2],me["grounded"] = s["jump_speed"],False
                jet = controls["boost"] and not me["grounded"] and me["energy"] > 0
                target = [controls["move"][i]*s["walk_speed"] for i in range(2)]
                dv = [target[i]-me["vel"][i] for i in range(2)]
                length = math.hypot(*dv)
                step = (s["ground_accel"] if me["grounded"] else s["air_accel"])*.05
                for i in range(2):
                    me["vel"][i] += dv[i]*min(1,step/max(.0001,length))
                old_z = me["pos"][2]
                if not me["grounded"]:
                    me["vel"][2] += ((s["jet_accel"] if jet else 0)-s["gravity"])*.05
                    me["vel"][2] = min(s["max_rise_speed"],me["vel"][2])
                q = [me["pos"][i]+me["vel"][i]*.05 for i in range(3)]
                if not world.body_clear(q[0],q[1],max(old_z,q[2]),s["radius"],s["height"],0):
                    q[0:2] = me["pos"][0:2]
                    me["vel"][0:2] = [0,0]
                surface = max([world.ground(*q[:2])]+[p.top for p in world.prisms if p.contains(*q[:2]) and p.top <= old_z+.001])
                if q[2] <= surface and me["vel"][2] <= 0:
                    q[2],me["vel"][2],me["grounded"] = surface,0,True
                else:
                    me["grounded"] = False
                me["pos"] = q
                if jet:
                    me["energy"] -= s["jet_drain"]*.05
                    last_spent = now
                elif now-last_spent > s["energy_regen_delay"]:
                    me["energy"] = min(me["max_energy"],me["energy"]+s["energy_regen"]*.05)
        self.fail(f"flight did not land: {me['pos']}, phase={escape.phase}")

    def test_climb_cross_and_land_with_acceleration_energy_feedback(self):
        for height in (12,25,40):
            with self.subTest(height=height):
                me,phases = self.flight_feedback(height)
                self.assertTrue(me["grounded"])
                self.assertAlmostEqual(me["pos"][2],height)
                self.assertGreater(me["energy"],0)
                self.assertTrue({"climb","cross","land","rest"} <= phases)

    def test_escape_does_not_fire_while_trying_to_regenerate(self):
        bot = Bot(self.h)
        bot.world = self.w
        bot.nav = Navigator(self.w,self.h["config"]["mech"])
        bot.combat = Combat(self.w,self.h["config"])
        bot.elevation = self.escape
        self.o["zone"].update(center=[0,0],radius=110,next_center=[0,0],next_radius=110,
                              shrink_start=500,shrink_end=550)
        p = self.o["self"]["pos"]
        self.o["mechs"] = [{"id":1,"kind":"mech","pos":[p[0],p[1]-45,0],"vel":[0,0,0],
                              "hp":1400,"max_hp":1400,"weapons":["gun"]}]
        self.o["offer"] = {"choices":[{"id":"sensors"},{"id":"servos"},{"id":"gun_rate"}]}
        action = bot.act(self.o)
        self.assertEqual(action["fire"],[False,False])
        self.assertEqual(bot.mode,"escape")
        self.assertIn(bot.elevation.phase,("approach","climb"))
        self.assertEqual(action["pick"],1)

    def test_escape_drops_mortar_against_laser_cookoff(self):
        bot = Bot(self.h)
        bot.world,bot.elevation = self.w,self.escape
        bot.nav = Navigator(self.w,self.h["config"]["mech"])
        self.o["zone"].update(center=[0,0],radius=110,next_center=[0,0],next_radius=110,
                              shrink_start=500,shrink_end=550)
        self.o["self"]["weapons"][1] = {"kind":"mortar","cooldown":0,
                                           "stats":self.h["config"]["weapons"]["mortar"]}
        p = self.o["self"]["pos"]
        self.o["mechs"] = [{"id":1,"kind":"mech","pos":[p[0],p[1]-45,0],"vel":[0,0,0],
                              "hp":1400,"max_hp":1400,"weapons":["gun","laser"]}]
        action = bot.act(self.o)
        self.assertEqual(action["drop"],1)
        self.assertEqual(action["fire"],[False,False])

    def test_sampled_public_map_roofs_with_flight_feedback(self):
        world = World(self.h["map"]["dir"])
        sites = RoofEscape(world,self.h["config"]["mech"]).sites
        self.assertGreater(len(sites),20)
        for index in (0,len(sites)//3,2*len(sites)//3,len(sites)-1):
            with self.subTest(site=index):
                me,phases = self.flight_feedback(sites[index]["landing"][2],world,index)
                self.assertTrue(me["grounded"])
                self.assertAlmostEqual(me["pos"][2],sites[index]["landing"][2])


if __name__ == "__main__":
    unittest.main()
