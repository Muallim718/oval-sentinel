"""Optional collection starts from observed repair, never an upgrade HP jump."""
import copy
from pathlib import Path
import time
import unittest
from test_bot import fixture,flat_world
from sentinel.geometry import World
from sentinel.navigation import Navigator
from sentinel.salvage import KillSalvage


class RegenerationCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hello,_=fixture()
        cls.world=World(Path(__file__).resolve().parents[1]/'arena')
        cls.nav=Navigator(cls.world,cls.hello['config']['mech'])

    def setUp(self):
        _,self.obs=fixture();self.me=self.obs['self'];self.now=106
        self.me.update(pos=[216.93009300054726,17.821556200825707,6.025353313975229],
            vel=[0,0,0],hp=400,max_hp=1512,energy=100,cubes=2,grounded=True,in_zone=True,upgrades=['armor'])
        self.me['stats']=copy.deepcopy(self.me['stats'])
        for key in ('radius','height','eye_height','muzzle_height'):self.me['stats'][key]*=1.1
        self.cubes=[dict(id=5002+i,pos=[181.068750583915,27.754120196151543,6.216980113594421])for i in range(5)]
        self.obs.update(t=self.now,tick=2120,cubes=self.cubes,mechs=[],events=[],projectiles=[],beams=[])
        self.salvage=KillSalvage(self.world,self.hello['config'],self.nav)
        self.salvage.record_kill(100,dict(id=2,kind='mech',pos=self.cubes[0]['pos']))

    def choose(self,threats=()):return self.salvage.choose(self.obs,self.cubes,threats,([0,0],470))

    def heal(self):
        for offset in (-.2,-.1,0):
            self.obs['t']=self.now+offset;self.me['hp']=400+45*offset
            self.choose()

    def test_no_optional_route_before_two_real_healing_increments(self):
        self.assertIsNone(self.choose())
        self.obs['t']+=.1;self.me['hp']+=4.5
        self.assertIsNone(self.choose())
        self.obs['t']+=.1;self.me['hp']+=4.5
        self.assertIsNotNone(self.choose(),self.salvage.reason)
        self.assertTrue(self.salvage.repair_collecting)
        self.assertFalse(self.salvage.sprint)

    def test_duplicate_observation_does_not_manufacture_healing(self):
        for _ in range(6):self.choose()
        self.assertFalse(self.salvage.regenerating)
        self.assertFalse(self.salvage.repair_collecting)

    def test_max_hp_cube_upgrade_or_unexplained_hp_jump_cannot_count(self):
        for changed in ('max_hp','cubes','upgrades','large_hp'):
            salvage=KillSalvage(self.world,self.hello['config'],self.nav)
            obs=copy.deepcopy(self.obs);me=obs['self'];salvage._observe_regeneration(obs)
            obs['t']+=.1;me['hp']+=4.5;salvage._observe_regeneration(obs)
            obs['t']+=.1;me['hp']+=4.5
            if changed=='max_hp':me['max_hp']+=56
            elif changed=='cubes':me['cubes']+=1
            elif changed=='upgrades':me['upgrades'].append('nanites')
            else:me['hp']+=50
            self.assertFalse(salvage._observe_regeneration(obs),changed)

    def test_real_damage_or_dealt_damage_stops_repair_authorization(self):
        self.heal();self.assertTrue(self.salvage.repair_collecting)
        for event in ('damaged','hit'):
            self.obs['t']+=.1;self.me['hp']+=4.5;self.obs['events']=[dict(type=event,amount=45)]
            self.assertIsNone(self.choose())
            self.assertFalse(self.salvage.repair_collecting)

    def test_late_bundle_must_still_be_currently_observed_and_substantial(self):
        self.heal();self.assertTrue(self.salvage.repair_collecting)
        self.obs['t']+=.1;self.me['hp']+=4.5;self.obs['cubes']=self.cubes[:3]
        self.assertIsNone(self.choose())
        self.assertFalse(self.salvage.repair_collecting)

    def test_kill_older_than_twelve_seconds_never_extends(self):
        self.now=113;self.heal()
        self.assertFalse(self.salvage.repair_collecting)
        self.assertIsNone(self.salvage.goal)

    def test_new_hunter_cancels_active_approach_on_pressure_or_race(self):
        self.heal();self.assertTrue(self.salvage.repair_collecting)
        enemy=dict(id=3,kind='mech',pos=[245,20,6],vel=[-10,0,0],aim=[3.14,0],weapons=['gun'],hp=1400)
        self.obs['t']+=.1;self.me['hp']+=4.5;self.obs['mechs']=[enemy]
        self.assertIsNone(self.choose([(enemy,1)]))
        self.assertFalse(self.salvage.repair_collecting)
        self.assertTrue('pressure' in self.salvage.reason or 'race' in self.salvage.reason)

    def test_screened_or_passive_far_actor_is_not_global_pressure_veto(self):
        enemy=dict(id=3,kind='mech',pos=[430,20,6],vel=[0,0,0],aim=[0,0],weapons=['gun'],hp=1400)
        self.assertFalse(self.salvage._recovery_pressure(self.obs,[(enemy,1)],[self.me['pos']],2.75,9.9,time.perf_counter()+1))

    def test_facing_but_out_of_weapon_range_is_not_an_immediate_lane_veto(self):
        enemy=dict(id=3,kind='mech',pos=[500,300,6],vel=[0,0,0],aim=[-2.35,0],weapons=['gun'],hp=1400)
        self.assertFalse(self.salvage._recovery_pressure(self.obs,[(enemy,1)],[self.me['pos']],2.75,9.9,time.perf_counter()+1))

    def test_second_public_corner_walks_to_late_observed_bundle(self):
        self.me['pos']=[148,46,self.world.ground(148,46)]
        point=[154,79,self.world.ground(154,79)]
        self.cubes=self.obs['cubes']=[dict(id=5100+i,pos=point)for i in range(5)]
        self.salvage=KillSalvage(self.world,self.hello['config'],self.nav)
        self.salvage.record_kill(100,dict(id=4,kind='mech',pos=point))
        self.heal()
        self.assertTrue(self.salvage.repair_collecting,self.salvage.reason)
        self.assertFalse(self.salvage.sprint)
        self.assertLessEqual(self.salvage.risk['eta'],4)
        self.assertGreater(self.obs['t']+self.salvage.risk['eta'],108)
        self.assertEqual(self.salvage.goal,(154,79))

    def test_original_fresh_direct_reward_does_not_need_healing_evidence(self):
        world=flat_world();self.me['pos']=[0,0,0]
        self.cubes=self.obs['cubes']=[dict(id=5100+i,pos=[10,0,0])for i in range(5)]
        self.salvage=KillSalvage(world,self.hello['config'])
        self.salvage.record_kill(100,dict(id=4,kind='mech',pos=[10,0,0]))
        self.assertEqual(self.choose(),(10,0))
        self.assertFalse(self.salvage.regenerating)
        self.assertFalse(self.salvage.repair_collecting)

    def test_route_gun_budget_includes_a_later_magazine_but_direct_is_unchanged(self):
        world=flat_world();salvage=KillSalvage(world,self.hello['config'])
        obs=copy.deepcopy(self.obs);obs['self'].update(pos=[0,0,0],aim=[0,0])
        obs['self']['stats']['armor']=0
        enemy=dict(id=3,kind='mech',pos=[100,0,0],aim=[3.14,0],vel=[0,0,0],weapons=['gun'],cubes=0,hp=1400)
        path=[(0,0,0)]*141;deadline=time.perf_counter()+1
        direct=salvage._future_damage(obs,path,7,[(enemy,1)],deadline)
        routed=salvage._future_damage(obs,path,7,[(enemy,1)],deadline,full_path=True)
        self.assertEqual(direct,12*45)
        self.assertEqual(routed,19*45)


if __name__=='__main__':unittest.main()
