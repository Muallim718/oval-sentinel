"""Routed verified rewards: exact anchors, growth, route budgets, and aborts."""
import copy
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from test_bot import fixture, flat_world, rectangle
from sentinel.geometry import World
from sentinel.navigation import Navigator
from sentinel.salvage import KillSalvage


class RoutedSalvageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hello,_=fixture()
        cls.world=World(Path(__file__).resolve().parents[1]/'arena')
        cls.nav=Navigator(cls.world,cls.hello['config']['mech'])

    def setUp(self):
        _,self.obs=fixture();self.me=self.obs['self']
        self.me.update(pos=[216.93009300054726,17.821556200825707,6.025353313975229],
            vel=[0,0,0],hp=197.55,max_hp=1512,energy=8.2,cubes=2,grounded=True,in_zone=True)
        self.me['stats']=copy.deepcopy(self.me['stats'])
        for key in ('radius','height','eye_height','muzzle_height'):
            self.me['stats'][key]*=1.1
        self.cubes=[dict(id=5002+i,pos=[181.068750583915,27.754120196151543,6.216980113594421])for i in range(5)]
        self.obs.update(t=10,tick=200,cubes=self.cubes,mechs=[],events=[],projectiles=[])
        self.salvage=KillSalvage(self.world,self.hello['config'],self.nav)
        self.salvage.record_kill(10,dict(id=2,kind='mech',pos=self.cubes[0]['pos']))
        self.circle=([0,0],470)

    def choose(self,threats=()):
        return self.salvage.choose(self.obs,self.cubes,threats,self.circle)

    def ready(self,threats=()):
        # Search slices can span observations, never authorize partial paths.
        goal=None
        for _ in range(4):
            goal=self.choose(threats)
            if goal is not None:break
        return goal

    def test_public_corner_has_complete_grown_body_route_and_exact_anchor(self):
        self.assertIsNotNone(self.ready(),self.salvage.reason)
        self.assertTrue(self.salvage.routed)
        self.assertGreater(self.salvage.risk['eta'],3)
        self.assertLess(self.salvage.risk['eta'],7)
        self.assertAlmostEqual(self.salvage.risk['healing'],280)
        self.assertEqual(self.salvage.risk['growth_cubes'],5)
        self.assertAlmostEqual(self.salvage.risk['future_radius'],3.375)
        self.assertLessEqual(self.salvage.risk['escape_energy'],8.2)
        goal=self.salvage.goal
        self.assertLessEqual(sum((a-b)**2 for a,b in zip(goal,self.cubes[0]['pos']))**.5,1.1)
        self.assertNotEqual(goal,self.salvage.waypoint[:2])
        self.assertIsNone(self.nav.search)
        self.assertFalse(self.nav.body_changed)

    def test_small_blocked_bundle_keeps_the_ordinary_direct_policy(self):
        self.cubes = self.obs["cubes"] = self.cubes[:3]
        with patch.object(self.salvage, "_detour", side_effect=AssertionError("small bundle cannot route")):
            self.assertIsNone(self.ready())
        self.assertFalse(self.salvage.routed)
        self.assertIsNone(self.salvage.waypoint)

    def test_coincident_cubes_share_one_blocked_direct_geometry_check(self):
        with (patch.object(self.world, "walk_clear", return_value=False) as direct,
              patch.object(self.salvage, "_detour", return_value=None) as detour):
            self.assertIsNone(self.choose())
        self.assertEqual(direct.call_count, 1)
        self.assertEqual(detour.call_count, 1)

    def test_expiry_covers_entire_detour_not_euclidean_approach(self):
        self.obs['t']=15
        self.assertIsNone(self.ready())
        self.assertIn('expires',self.salvage.reason)

    def test_competitor_race_uses_detour_eta_and_aborts_active_route(self):
        self.assertIsNotNone(self.ready(),self.salvage.reason)
        enemy=dict(id=3,kind='mech',pos=[200,40,6],vel=[0,0,0],weapons=['gun'],hp=1400)
        self.assertIsNone(self.choose([(enemy,1)]))
        self.assertIn('race',self.salvage.reason)
        self.assertIsNone(self.salvage.waypoint)

    def test_whole_detour_must_remain_inside_future_circle(self):
        self.circle=([181.07,27.75],15)
        self.assertIsNone(self.ready())
        self.assertIn('zone',self.salvage.reason)

    def test_fresh_confirmation_and_emergency_remain_mandatory(self):
        self.salvage.beacons=[]
        self.assertIsNone(self.ready())
        self.assertIn('verified',self.salvage.reason)
        self.salvage.record_kill(10,dict(id=2,kind='mech',pos=self.cubes[0]['pos']))
        self.assertIsNone(self.salvage.choose(self.obs,self.cubes,[],self.circle,emergency=True))
        self.assertIsNone(self.salvage.waypoint)

    def test_budget_failure_cannot_authorize_a_partial_route(self):
        self.salvage.SEARCH_SECONDS=-.011
        self.assertIsNone(self.choose())
        self.assertIsNone(self.salvage.waypoint)

    def test_no_astar_slice_starts_without_its_whole_remaining_budget(self):
        with patch.object(Navigator,'plan',side_effect=AssertionError('must not start A*')):
            result=self.salvage._detour(self.me,self.cubes[0],self.cubes,self.circle,time.perf_counter()+.005)
        self.assertIsNone(result)
        self.assertIn('budget',self.salvage.reason)

    def test_future_cube_trap_stays_rejected_with_routing_enabled(self):
        world=flat_world([rectangle(-15,-30,15,-3.1),rectangle(-15,3.1,15,30)])
        nav=Navigator(world,self.hello['config']['mech'])
        me=self.me;me.update(pos=[-30,0,0],cubes=0,hp=650,max_hp=1400,energy=100)
        me['stats']=copy.deepcopy(self.hello['config']['mech'])
        self.cubes=self.obs['cubes']=[dict(id=7000+i,pos=[0,(i-2)*.1,0])for i in range(5)]
        self.salvage=KillSalvage(world,self.hello['config'],nav)
        self.salvage.record_kill(10,dict(id=2,kind='mech',pos=[0,0,0]))
        self.assertIsNone(self.ready())
        self.assertIn('anchor',self.salvage.reason)

    def test_extra_known_cube_beside_detour_enlarges_the_planning_body(self):
        self.cubes.append(dict(id=9000,pos=[250,90,self.world.ground(250,90)]))
        self.assertIsNotNone(self.ready(),self.salvage.reason)
        self.assertEqual(self.salvage.risk['growth_bound'],6)
        self.assertAlmostEqual(self.salvage.risk['future_radius'],3.5)
        self.assertEqual(self.salvage.risk['growth_cubes'],5)

    def test_every_original_direct_candidate_precedes_optional_detour(self):
        world=flat_world([rectangle(-5,-20,5,20)])
        self.me.update(pos=[-30,0,0],vel=[0,0,0],cubes=0,hp=650,max_hp=1400,energy=100)
        self.me['stats']=copy.deepcopy(self.hello['config']['mech'])
        self.cubes=self.obs['cubes']=[dict(id=7000+i,pos=[30,0,0])for i in range(5)]
        self.cubes.append(dict(id=8000,pos=[-30,65,0]))
        self.salvage=KillSalvage(world,self.hello['config'],Navigator(world,self.hello['config']['mech']))
        self.salvage.record_kill(10,dict(id=2,kind='mech',pos=[30,0,0]))
        self.salvage.record_kill(10,dict(id=4,kind='mech',pos=[-30,65,0]))
        self.assertEqual(self.choose(),(-30,65))
        self.assertFalse(self.salvage.routed)

    def test_full_detour_checks_a_late_real_ballistic_mortar_packet(self):
        salvage=KillSalvage(flat_world(),self.hello['config'])
        gravity=self.hello['config']['weapons']['mortar']['gravity']
        self.obs['projectiles']=[dict(id=999,kind='mortar',pos=[20,-144,5+2*gravity],vel=[0,72,0])]
        path=[(.5*i,0,0)for i in range(141)]
        deadline=time.perf_counter()+1
        self.assertEqual(salvage._projectile_damage(self.obs,path,2.5,9,deadline),0)
        self.assertGreater(salvage._projectile_damage(self.obs,path,2.5,9,deadline,full_path=True),0)

    def test_future_healing_cannot_pay_for_lethal_damage_before_pickup(self):
        self.me['hp']=400
        self.cubes.extend(dict(id=6000+i,pos=self.cubes[0]['pos'])for i in range(5))
        self.obs['cubes']=self.cubes
        with patch.object(self.salvage,'_future_damage',return_value=430):
            self.assertIsNone(self.ready())
        self.assertIn('lethal before pickup',self.salvage.reason)


if __name__=='__main__':unittest.main()
