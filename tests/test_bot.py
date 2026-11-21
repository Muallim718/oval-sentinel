"""Behavioral regressions: geometry, escape routing, aiming, and survival choices."""
from array import array
import copy
import gzip
import json
import math
from pathlib import Path
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentinel.combat import Combat, intercept
from sentinel.geometry import Prism, World, angle_error
from sentinel.navigation import Navigator
from sentinel.strategy import Bot, future_circle
from sentinel.memory import LootMemory
from sentinel.elevation import RoofEscape


def flat_world(prisms=()):
    w = World.__new__(World)
    w.bounds = {"minX":-120,"maxX":120,"minY":-120,"maxY":120}
    w.terrain = {"minX":-125,"minY":-125,"step":1,"nx":251,"ny":251,"scale":0.01}
    w.heights = array("h", [0])*(251*251)
    w.prisms = list(prisms)
    w.buckets = {}
    for index, p in enumerate(prisms):
        a,b,c,d = p.bounds
        for j in range(math.floor(b/w.CELL), math.floor(d/w.CELL)+1):
            for i in range(math.floor(a/w.CELL), math.floor(c/w.CELL)+1):
                w.buckets.setdefault((i,j), []).append(index)
    return w


def rectangle(x1,y1,x2,y2,base=0,top=20,holes=None):
    return Prism({"base":base,"top":top,"ring":[x1,y1,x2,y1,x2,y2,x1,y2],"holes":holes or []})


def fixture():
    with gzip.open(ROOT/"check/stream.jsonl.gz", "rt", encoding="utf-8") as f:
        h = json.loads(next(f))
        o = json.loads(next(f))
    h["map"]["dir"] = str(ROOT/"arena")
    return h, o


class GeometryTests(unittest.TestCase):
    def test_wall_stops_shots_but_roof_does_not_stop_high_shots(self):
        w = flat_world([rectangle(-2,-15,2,15)])
        self.assertFalse(w.line_clear((-30,0,7),(30,0,7)))
        self.assertTrue(w.line_clear((-30,0,25),(30,0,25)))

    def test_courtyard_is_open_and_edges_solid(self):
        p = rectangle(-20,-20,20,20,holes=[[-10,-10,10,-10,10,10,-10,10]])
        self.assertFalse(p.overlaps(0,0,2.5))
        self.assertTrue(p.overlaps(9,0,2.5))
        self.assertFalse(p.blocks_segment((-4,0,5),(4,0,5)))
        self.assertTrue(p.blocks_segment((-30,0,5),(0,0,5)))

    def test_bridge_clearance_and_rooftop(self):
        w = flat_world([rectangle(-10,-10,10,10,base=12,top=14)])
        self.assertTrue(w.body_clear(0,0,0,height=9))
        self.assertFalse(w.body_clear(0,0,5,height=9))
        self.assertTrue(w.body_clear(0,0,14,height=9))

    def test_body_radius_and_map_boundary(self):
        w = flat_world([rectangle(0,-10,20,10)])
        self.assertTrue(w.body_clear(-3,0,0,radius=2.5))
        self.assertFalse(w.body_clear(-3,0,0,radius=4))
        self.assertFalse(w.body_clear(119,0,0,radius=2.5))

    def test_thin_wall_and_sloping_ray(self):
        w = flat_world([rectangle(-0.1,-10,0.1,10)])
        self.assertFalse(w.walk_clear((-6,0,0),(6,0,0)))
        self.assertTrue(w.line_clear((-10,0,7),(10,0,50)))
        self.assertFalse(w.line_clear((-10,0,7),(10,0,15)))

    def test_bilinear_ground(self):
        w = flat_world()
        k = 125*251+125
        w.heights[k],w.heights[k+1] = 0,100
        w.heights[k+251],w.heights[k+252] = 200,300
        self.assertAlmostEqual(w.ground(.5,.5),1.5)


class NavigationTests(unittest.TestCase):
    def test_route_goes_around_wall_and_all_segments_are_clear(self):
        w = flat_world([rectangle(-3,-35,3,35)])
        nav = Navigator(w,{"radius":2.5,"height":9,"step_up":1.2})
        path = []
        for _ in range(100):
            path = nav.plan((-65,0,0),(65,0),((0,0),150))
            if nav.search_done:
                break
        self.assertTrue(nav.search_done)
        self.assertGreater(len(path),2)
        self.assertLess(math.dist(path[-1][:2],(65,0)),9)
        self.assertGreater(max(abs(p[1]) for p in path),35)
        for a,b in zip([(-65,0,0)]+path,path):
            self.assertTrue(w.walk_clear(a,b,radius=2.9))

    def test_search_can_escape_u_shape_instead_of_greedy_dead_end(self):
        w = flat_world([rectangle(0,-35,5,35),rectangle(-40,-40,5,-35),rectangle(-40,35,5,40)])
        nav = Navigator(w,{"radius":2.5,"height":9,"step_up":1.2})
        for _ in range(150):
            path = nav.plan((-15,0,0),(35,0),((0,0),150))
            if nav.search_done:
                break
        self.assertTrue(nav.search_done)
        self.assertLess(math.dist(path[-1][:2],(35,0)),9)
        self.assertLess(min(p[0] for p in path),-40)


class WeaponTests(unittest.TestCase):
    def setUp(self):
        self.hello,self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.combat = Combat(self.world,self.config)
        self.me = self.obs["self"]
        self.me.update(pos=[-90,0,0],aim=[0,0])
        self.enemy = {"kind":"mech","id":1,"pos":[10,0,0],"vel":[0,10,0],"hp":1400,"max_hp":1400}

    def weapon(self,kind,**extra):
        return {"kind":kind,"stats":copy.deepcopy(self.config["weapons"][kind]),"cooldown":0,**extra}

    def test_intercept_really_meets_moving_target(self):
        t = intercept([0,0,0],[100,0,0],[0,20,0],100)
        self.assertAlmostEqual(math.hypot(100,20*t),100*t)
        self.assertEqual(intercept([0,0,0],[100,0,0],[200,0,0],100),0)

    def test_gun_leads_and_waits_for_actual_torso(self):
        gun = self.weapon("gun",ammo=12,reload=0)
        self.me["weapons"] = [gun,None]
        aim,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertGreater(aim[0],0.02)
        self.assertFalse(fire[0])
        self.me["aim"] = aim
        _,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertTrue(fire[0])

    def test_laser_charges_then_releases_at_full_charge(self):
        laser = self.weapon("laser",charge=0)
        self.me["weapons"] = [None,laser]
        self.enemy["vel"] = [0,0,0]
        aim,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertTrue(fire[1])
        self.me["aim"] = aim
        laser["charge"] = laser["stats"]["charge"]
        _,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertFalse(fire[1])
        self.me["aim"] = [math.pi,0]
        _,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertTrue(fire[1])

    def test_lightning_never_fires_out_of_range_or_without_energy(self):
        self.me["weapons"] = [None,self.weapon("lightning")]
        _,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertFalse(fire[1])
        self.enemy["pos"] = [-65,0,0]
        self.me["energy"] = 0
        _,fire,_ = self.combat.action(self.me,[self.enemy],False,False)
        self.assertFalse(fire[1])

    def test_no_shooting_through_building(self):
        combat = Combat(flat_world([rectangle(-30,-20,-25,20)]),self.config)
        self.assertIsNone(combat.solve(self.me,self.enemy,self.weapon("gun",ammo=12,reload=0)))

    def test_gun_keeps_tracking_and_trigger_during_cooldown(self):
        gun = self.weapon("gun",ammo=5,reload=0)
        gun["cooldown"] = 0.19
        self.me["weapons"] = [gun,None]
        desired = self.combat.solve(self.me,self.enemy,gun)[0]
        self.me["aim"] = desired
        aim,fire,target = self.combat.action(self.me,[self.enemy],False,False)
        self.assertIsNotNone(aim)
        self.assertEqual(target["id"],self.enemy["id"])
        self.assertTrue(fire[0])

    def test_mortar_ballistics_and_self_splash_exclusion(self):
        mortar = self.weapon("mortar")
        self.enemy["vel"] = [0,0,0]
        solved = self.combat.solve(self.me,self.enemy,mortar)
        self.assertIsNotNone(solved)
        pitch = solved[0][1]
        speed,g = mortar["stats"]["speed"],mortar["stats"]["gravity"]
        t = 100/(speed*math.cos(pitch))
        self.assertAlmostEqual(9.5+speed*math.sin(pitch)*t-g*t*t/2,4.5,places=4)
        self.enemy["pos"] = [-85,0,0]
        self.assertIsNone(self.combat.solve(self.me,self.enemy,mortar))


class StrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hello,cls.initial = fixture()

    def setUp(self):
        self.obs = copy.deepcopy(self.initial)
        self.bot = Bot(copy.deepcopy(self.hello))

    def test_zone_prediction_does_not_double_apply_elapsed_shrink(self):
        zone = {"center":[50,0],"radius":150,"next_center":[100,0],"next_radius":100,
                "shrink_start":0,"shrink_end":100}
        c,r = future_circle(zone,50,25)
        self.assertEqual(c,[75,0])
        self.assertEqual(r,125)
        self.assertEqual(future_circle(zone,50,200),([100,0],100))

    def test_defensive_upgrade_is_selected(self):
        self.obs["offer"] = {"choices":[{"id":"sensors"},{"id":"servos"},{"id":"gun_rate"}]}
        self.assertEqual(self.bot.act(self.obs)["pick"],1)

    def test_loot_pickup_checks_vertical_separation(self):
        p = self.obs["self"]["pos"]
        self.obs["pickups"] = [{"id":8001,"kind":"laser","pos":[p[0],p[1],p[2]+20]}]
        self.assertNotIn("take",self.bot.act(self.obs))
        self.obs["pickups"][0]["pos"][2] = p[2]
        self.assertEqual(self.bot.act(self.obs)["take"],8001)

    def test_hurt_bot_avoids_optional_long_range_fight(self):
        p = self.obs["self"]["pos"]
        self.obs["self"]["hp"] = 400
        self.obs["mechs"] = [{"id":1,"kind":"mech","pos":[p[0]-110,p[1],p[2]],
                              "vel":[0,0,0],"aim":[0,0],"hp":1400,"max_hp":1400}]
        action = self.bot.act(self.obs)
        self.assertEqual(action["fire"],[False,False])
        self.assertLess(abs(angle_error(action["aim"][0],math.pi)),0.01)

    def test_bot_is_deterministic_given_same_input_and_seed(self):
        a = self.bot.act(self.obs)
        b = Bot(copy.deepcopy(self.hello)).act(copy.deepcopy(self.obs))
        self.assertEqual(a,b)

    def test_live_weapon_speed_changes_lead(self):
        combat = self.bot.combat
        me = copy.deepcopy(self.obs["self"])
        me["pos"] = [320,-280,-2]
        enemy = {"kind":"mech","pos":[220,-280,-2],"vel":[0,10,0]}
        weapon = copy.deepcopy(me["weapons"][0])
        a = combat.solve(me,enemy,weapon)
        weapon["stats"]["speed"] *= 2
        b = combat.solve(me,enemy,weapon)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertLess(abs(math.pi-abs(b[0][0])),abs(math.pi-abs(a[0][0])))

    def test_missing_map_exits_instead_of_claiming_ready(self):
        hello = copy.deepcopy(self.hello)
        hello["map"]["dir"] = str(ROOT/"this-map-does-not-exist")
        result = subprocess.run([sys.executable,"-u",str(ROOT/"bot.py")],
                                input=json.dumps(hello)+"\n", capture_output=True,
                                text=True, timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('"ready"',result.stdout)
        self.assertIn("FileNotFoundError",result.stderr)


class TacticalRegressionTests(unittest.TestCase):
    """Controlled feedback tests, not a replacement for the server simulation."""

    def setUp(self):
        self.hello,self.obs = fixture()
        self.bot = Bot(self.hello)
        self.world = flat_world()
        self.replace_world(self.world)
        self.obs["self"].update(pos=[-70,0,0],vel=[0,0,0],aim=[0,0],hp=1400)
        self.obs["zone"].update(center=[0,0],radius=118,next_center=[0,0],next_radius=118,
                                shrink_start=500,shrink_end=550)

    def replace_world(self,world):
        self.bot.world = world
        self.bot.nav = Navigator(world,self.hello["config"]["mech"])
        self.bot.combat = Combat(world,self.hello["config"])
        self.bot.elevation = RoofEscape(world,self.hello["config"]["mech"])

    def enemy(self,x=0,hp=1400):
        return {"id":1,"kind":"mech","pos":[x,0,0],"vel":[0,0,0],"aim":[math.pi,0],
                "hp":hp,"max_hp":1400,"weapons":["gun"]}

    def test_never_reload_partial_magazine_while_tracking_enemy(self):
        self.obs["mechs"] = [self.enemy()]
        gun = self.obs["self"]["weapons"][0]
        gun.update(ammo=5,cooldown=0.2)
        action = self.bot.act(self.obs)
        self.assertFalse(action["reload"])
        self.assertNotEqual(action["aim"],[0,0])

    def test_quiet_reload_and_empty_reload_still_work(self):
        gun = self.obs["self"]["weapons"][0]
        gun["ammo"] = 5
        self.assertTrue(self.bot.act(self.obs)["reload"])
        gun["ammo"] = 0
        self.obs["mechs"] = [self.enemy()]
        self.assertTrue(self.bot.act(self.obs)["reload"])

    def test_remember_weapon_after_looking_away(self):
        item = {"id":8001,"kind":"laser","pos":[-10,0,0]}
        self.obs["pickups"] = [item]
        self.bot.act(self.obs)
        self.assertEqual(self.bot.goal_kind,"weapon")
        original_goal = self.bot.goal
        self.obs.update(t=2,tick=40,pickups=[])
        self.bot.act(self.obs)
        self.assertEqual(self.bot.goal,original_goal)
        self.assertEqual(self.bot.goal_kind,"weapon")
        self.assertEqual(len(self.bot.loot.get("pickups")),1)

    def test_missing_nearby_loot_is_not_pursued_forever(self):
        self.obs["cubes"] = [{"id":5001,"pos":[-68,0,0]}]
        memory = LootMemory()
        memory.update(self.obs,self.world)
        self.obs.update(t=1,tick=20,cubes=[])
        memory.update(self.obs,self.world)
        self.assertEqual(memory.get("cubes"),[])

    def test_weapon_objectives_still_available_at_cube_stat_cap(self):
        self.obs["self"]["cubes"] = 10
        self.obs["pickups"] = [{"id":8001,"kind":"laser","pos":[-10,0,0]}]
        self.bot.act(self.obs)
        self.assertEqual(self.bot.goal_kind,"weapon")

    def test_recovery_hysteresis_does_not_restart_fight_at_60_percent(self):
        me = self.obs["self"]
        me["hp"] = 700
        self.bot.select_mode(self.obs)
        self.assertTrue(self.bot.recovering)
        me["hp"] = 1000
        self.bot.select_mode(self.obs)
        self.assertTrue(self.bot.recovering)
        me["hp"] = 1300
        self.bot.select_mode(self.obs)
        self.assertFalse(self.bot.recovering)

    def test_lightning_closes_distance_in_favorable_duel(self):
        me = self.obs["self"]
        me["weapons"][1] = {"kind":"lightning","cooldown":0,
                            "stats":copy.deepcopy(self.hello["config"]["weapons"]["lightning"])}
        self.obs["mechs"] = [self.enemy()]
        action = self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,"fight")
        self.assertLess(self.bot.fight_range,45)
        self.assertGreater(action["move"][0],0)

    def test_crossfire_does_not_trigger_an_aggressive_duel(self):
        self.obs["mechs"] = [self.enemy(),{**self.enemy(10),"id":2}]
        self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,"evade")
        self.assertIsNone(self.bot.duel)

    def test_replace_mortar_with_lightning_without_dropping_gun(self):
        self.obs["self"]["weapons"][1] = {"kind":"mortar","cooldown":0,
                "stats":copy.deepcopy(self.hello["config"]["weapons"]["mortar"])}
        self.obs["pickups"] = [{"id":8001,"kind":"lightning","pos":[-70,0,0]}]
        action = self.bot.act(self.obs)
        self.assertEqual(action["take"],8001)
        self.assertEqual(action["drop"],1)

    def test_collect_cube_around_wall_with_movement_feedback(self):
        self.replace_world(flat_world([rectangle(-4,-25,4,25)]))
        me = self.obs["self"]
        cube = {"id":5001,"pos":[30,0,0]}
        self.obs["cubes"] = [cube]
        collected = False
        for decision in range(250):
            self.obs.update(t=decision*.1,tick=decision*2)
            # Turned-away loot vanishes from the observation; memory must retain it.
            near_and_visible = math.dist(me["pos"],cube["pos"]) < 45 and self.bot.world.line_clear(
                [*me["pos"][:2],8],[*cube["pos"][:2],1])
            self.obs["cubes"] = [cube] if decision < 3 or near_and_visible else []
            action = self.bot.act(self.obs)
            new_pos = [me["pos"][0]+action["move"][0]*1.17,
                       me["pos"][1]+action["move"][1]*1.17,0]
            if self.bot.world.walk_clear(me["pos"],new_pos):
                me["vel"] = [action["move"][0]*11.7,action["move"][1]*11.7,0]
                me["pos"] = new_pos
            else:
                me["vel"] = [0,0,0]
            me["aim"] = action["aim"]
            if math.dist(me["pos"],cube["pos"]) < 3.5:
                collected = True
                break
        self.assertTrue(collected,f"failed to collect cube: pos={me['pos']}, goal={self.bot.goal}")

    def test_full_magazine_fire_rate_with_weapon_feedback(self):
        # Stationary, unobstructed target; a two-tick weapon-clock model from the
        # published rates verifies our reload policy, not the full game physics.
        me = self.obs["self"]
        self.obs["mechs"] = [self.enemy()]
        gun = me["weapons"][0]
        rounds = 0
        early_reloads = 0
        for decision in range(130):
            self.obs.update(t=decision*.1,tick=decision*2)
            action = self.bot.act(self.obs)
            me["aim"] = action["aim"]
            if action.get("reload",False) and gun["reload"] == 0:
                early_reloads += gun["ammo"] > 0
                gun["reload"] = gun["stats"]["reload"]
            for _ in range(2):
                was_reloading = gun["reload"] > 0
                gun["reload"] = max(0,gun["reload"]-.05)
                gun["cooldown"] = max(0,gun["cooldown"]-.05)
                if was_reloading and gun["reload"] == 0:
                    gun["ammo"] = gun["stats"]["mag"]
                if action["fire"][0] and gun["cooldown"] <= 1e-8 and gun["reload"] == 0 and gun["ammo"] > 0:
                    rounds += 1
                    gun["ammo"] -= 1
                    gun["cooldown"] = gun["stats"]["cooldown"]
        self.assertEqual(early_reloads,0)
        self.assertGreaterEqual(rounds,30)


if __name__ == "__main__":
    unittest.main()
