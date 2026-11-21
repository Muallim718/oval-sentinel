"""Independent 20 Hz post-kill collection feedback, not scored-match simulation.

The victim dies from a real modeled gun hit. Its public cube count determines
the reward. A live gun hunter continues firing/pursuing during collection.
"""
import copy
import math
from pathlib import Path
import sys
import unittest

from test_bot import ROOT,flat_world,rectangle
sys.path.insert(0,str(ROOT/'tools'))
from ground_lab import Lab,DT,lead
from sentinel.geometry import distance
from sentinel.navigation import Navigator
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering


class SalvageFeedback(Lab):
    def __init__(self,case='viable',seconds=3):
        super().__init__(ROOT,'open_pursuit',11,seconds)
        self.case=case
        prisms=[]
        if case=='narrow':
            prisms=[rectangle(-15,-25,15,-3.1),rectangle(-15,3.1,15,25)]
        self.world=flat_world(prisms)
        self.bot.world=self.world
        self.bot.nav=Navigator(self.world,self.config['mech'])
        self.bot.combat=Combat(self.world,self.config)
        self.bot.cover=CoverPlanner(self.world,self.config)
        self.bot.motion=GroundSteering(self.world,self.config)
        if hasattr(self.bot,'salvage'):
            from sentinel.salvage import KillSalvage
            self.bot.salvage=KillSalvage(self.world,self.config)
        player_x,victim_x,hunter_x=(-30,-15,80)
        if case=='small_bundle':
            player_x,victim_x,hunter_x=(-30,-20,80)
        elif case=='race':
            player_x,victim_x,hunter_x=(-45,-15,-8)
        elif case=='narrow':
            player_x,victim_x,hunter_x=(-35,0,80)
        self.me=self.entity(0,[player_x,0,0],650)
        self.victim=self.entity(1,[victim_x,0,0],40)
        self.hunter=self.entity(2,[hunter_x,0,0],1400)
        self.set_cubes(self.victim,0 if case=='small_bundle' else 3)
        self.victim['hp']=40
        self.victim['weapons'][0].update(ammo=0,reload=2.0)
        self.entities=[self.me,self.victim,self.hunter]
        self.enemies=[self.victim,self.hunter]
        self.enemy_nav={e['id']:Navigator(self.world,self.config['mech']) for e in self.enemies}
        for entity,target in ((self.me,self.victim),(self.hunter,self.me)):
            origin=[*entity['pos'][:2],entity['stats']['muzzle_height']]
            point=[*target['pos'][:2],target['stats']['height']/2]
            entity['aim']=lead(origin,point,target['vel'],entity['weapons'][0]['stats']['speed'])
        self.loot=[]
        self.reward_spawned=False
        self.cube_healing=0.0
        self.energy_spent=0.0
        self.energy_regenerated=0.0
        self.pickup_times=[]
        self.first_hunter_hit=None
        self.near_hunter_at=None
        self.growth_collision=False
        self.salvage_frames=0
        self.trace=[]
        if case=='zone':
            self.zone.update(center=[0,0],radius=117,next_center=[60,0],next_radius=35,
                             shrink_start=100,shrink_end=104)

    def set_cubes(self,entity,total):
        config=self.config['cubes'];base=self.config['mech']
        old_max=entity['max_hp'];capped=min(total,config['stat_cap'])
        entity['cubes']=total
        entity['max_hp']=base['hp']*(1+config['hp_per_cube']*capped)
        healed=entity['max_hp']-old_max
        entity['hp']=min(entity['max_hp'],entity['hp']+healed)
        size=1+config['size_per_cube']*total
        for key in ('radius','height','eye_height','muzzle_height'):
            entity['stats'][key]=base[key]*size
        entity['stats']['hp']=entity['max_hp']
        entity['weapons'][0]['stats']['damage']=self.config['weapons']['gun']['damage']*(
            1+config['damage_per_cube']*capped)
        return healed

    def move_entity(self,entity,action):
        before=entity['energy']
        # A stationary boost command does not spend ground sprint energy.
        if (entity['grounded'] and math.hypot(*action.get('move',[0,0]))<1e-6 and
                math.hypot(*entity['vel'][:2])<1e-6):
            action={**action,'boost':False}
        super().move_entity(entity,action)
        if entity['id']==0:
            self.energy_spent+=max(0,before-entity['energy'])
            self.energy_regenerated+=max(0,entity['energy']-before)

    def pickups(self):
        remaining=[]
        for cube in self.loot:
            eligible=[e for e in self.entities if e['hp']>0 and
                      distance(e['pos'],cube['pos'])<=self.config['cubes']['pickup_radius'] and
                      abs(e['pos'][2]-cube['pos'][2])<=4]
            if not eligible:
                remaining.append(cube);continue
            winner=min(eligible,key=lambda e:(distance(e['pos'],cube['pos']),e['id']))
            healed=self.set_cubes(winner,winner['cubes']+1)
            if winner['id']==0:
                self.cube_healing+=healed
                self.pickup_times.append(self.t-100)
                self.events.append(dict(type='pickup',cubes=winner['cubes']))
        self.loot=remaining
        self.growth_collision|=not self.world.body_clear(*self.me['pos'],
            self.me['stats']['radius']-.001,self.me['stats']['height'],0)

    def run(self):
        action={}
        for tick in range(round(self.seconds/DT)):
            self.t=100+tick*DT
            if tick%2==0:
                observation=self.observation(tick);observation['alive']=16
                action=self.bot.act(observation)
                controller=getattr(self.bot,'salvage',None)
                state=getattr(controller,'state','absent')
                self.salvage_frames+=state=='collect'
                self.metrics['ignored_jump_requests']+=bool(action.get('jump'))
                self.trace.append(dict(t=round(self.t-100,3),pos=list(self.me['pos']),
                    hp=self.me['hp'],cubes=self.me['cubes'],salvage=state,
                    reason=getattr(controller,'reason',None),goal=self.bot.goal,
                    move=action['move'],boost=action.get('boost',False)))
            actions={0:action,1:dict(move=[0,0],boost=False,aim=self.victim['aim'],
                                     fire=[False,False],reload=False),
                     2:self.enemy_action(self.hunter,tick)}
            for entity in self.entities:
                if entity['hp']>0:
                    self.move_entity(entity,actions[entity['id']])
                    self.weapon(entity,actions[entity['id']])
            self.projectiles()
            if self.victim['hp']<=0 and not self.reward_spawned:
                self.reward_spawned=True
                count=self.victim['cubes']+self.config['cubes']['death_drop_extra']
                self.loot=[dict(id=5000+i,pos=list(self.victim['pos'])) for i in range(count)]
            if self.first_hunter_hit is None and any(e['type']=='damaged' and e.get('by')==2
                                                     for e in self.events):
                self.first_hunter_hit=self.t-100
            if self.near_hunter_at is None and distance(self.me['pos'],self.hunter['pos'])<60:
                self.near_hunter_at=self.t-100
            self.pickups()
            if self.me['hp']<=0 or self.growth_collision:
                break
        return dict(case=self.case,reward_spawned=self.reward_spawned,cubes=self.me['cubes'],
                    hunter_cubes=self.hunter['cubes'],cube_healing=self.cube_healing,
                    hp=self.me['hp'],max_hp=self.me['max_hp'],radius=self.me['stats']['radius'],
                    gun_damage=self.me['weapons'][0]['stats']['damage'],
                    energy=self.me['energy'],energy_spent=self.energy_spent,
                    energy_regenerated=self.energy_regenerated,
                    first_pickup=min(self.pickup_times,default=None),
                    first_hunter_hit=self.first_hunter_hit,near_hunter_at=self.near_hunter_at,
                    damage_taken=self.metrics['damage_taken'],
                    damage_dealt=self.metrics['damage_dealt'],salvage_frames=self.salvage_frames,
                    ignored_jumps=self.metrics['ignored_jump_requests'],
                    growth_collision=self.growth_collision,trace=self.trace)


class SalvageFeedbackTests(unittest.TestCase):
    def test_recovering_exposed_kill_bundle_is_collected_before_next_hunter(self):
        result=SalvageFeedback('viable',3).run()
        self.assertTrue(result['reward_spawned'])
        self.assertEqual(result['cubes'],5)
        self.assertAlmostEqual(result['cube_healing'],280)
        self.assertAlmostEqual(result['max_hp'],1680)
        self.assertAlmostEqual(result['radius'],3.125)
        self.assertAlmostEqual(result['gun_damage'],54)
        self.assertIsNotNone(result['first_hunter_hit'])
        self.assertGreater(result['salvage_frames'],0)
        self.assertGreater(result['hp'],0)
        self.assertEqual(result['ignored_jumps'],0)
        self.assertFalse(result['growth_collision'])
        self.assertAlmostEqual(result['energy'],100-result['energy_spent']+
                               result['energy_regenerated'],places=5)

    def test_even_an_unfed_victims_two_cube_reward_can_be_collected(self):
        result=SalvageFeedback('small_bundle',3).run()
        self.assertTrue(result['reward_spawned'])
        self.assertEqual(result['cubes'],2)
        self.assertAlmostEqual(result['cube_healing'],112)
        self.assertAlmostEqual(result['max_hp'],1512)
        self.assertAlmostEqual(result['radius'],2.75)
        self.assertGreater(result['salvage_frames'],0)
        self.assertEqual(result['ignored_jumps'],0)
        self.assertFalse(result['growth_collision'])

    def test_hunter_winning_pickup_race_prevents_a_losing_collection_commitment(self):
        result=SalvageFeedback('race',3).run()
        self.assertTrue(result['reward_spawned'])
        self.assertEqual(result['cubes'],0)
        self.assertEqual(result['salvage_frames'],0)
        self.assertEqual(result['ignored_jumps'],0)
        self.assertFalse(result['growth_collision'])

    def test_cube_growth_cannot_silently_pass_a_narrow_return_corridor(self):
        result=SalvageFeedback('narrow',4).run()
        self.assertTrue(result['reward_spawned'])
        self.assertFalse(result['growth_collision'],'prospective cube growth intersects a wall')
        self.assertEqual(result['cubes'],0)
        self.assertEqual(result['salvage_frames'],0)

    def test_urgent_zone_rotation_is_not_replaced_by_a_post_kill_detour(self):
        result=SalvageFeedback('zone',2).run()
        self.assertTrue(result['reward_spawned'])
        self.assertEqual(result['salvage_frames'],0)
        self.assertFalse(result['growth_collision'])


if __name__=='__main__':
    unittest.main()
