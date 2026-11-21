"""Reactive gun/laser corner feedback, not authoritative or scored simulation.

Actual charge clocks, movement penalty, torso slew, muzzle ray and cylinder hits
are resolved at20Hz. Enemy tracking is earned by a real prior eye sightline.
"""
import copy
import math
import sys
import unittest

from test_bot import ROOT,flat_world,rectangle
sys.path.insert(0,str(ROOT/'tools'))
from ground_lab import Lab,DT,lead,cylinder_entry,wrapped
from sentinel.geometry import distance
from sentinel.navigation import Navigator
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner,firing_lane
from sentinel.movement import GroundSteering


class AmbushFeedback(Lab):
    def __init__(self,case='corner',seconds=8,reported_total_charge=False):
        super().__init__(ROOT,'open_pursuit',11,seconds)
        self.case=case
        self.reported_total_charge=reported_total_charge
        self.world=flat_world([rectangle(-3,-45,3,45,top=20)])
        self.bot.world=self.world
        self.bot.nav=Navigator(self.world,self.config['mech'])
        self.bot.combat=Combat(self.world,self.config)
        self.bot.cover=CoverPlanner(self.world,self.config)
        self.bot.motion=GroundSteering(self.world,self.config)
        if hasattr(self.bot,'salvage'):
            from sentinel.salvage import KillSalvage
            self.bot.salvage=KillSalvage(self.world,self.config)
        if hasattr(self.bot,'ambush'):
            from sentinel.ambush import AmbushPlanner
            self.bot.ambush=AmbushPlanner(self.world,self.config)
        self.me=self.entity(0,[-12,-39,0],1400)
        self.me['weapons'][1]=dict(kind='laser',cooldown=0,charge=0,
                                  stats=copy.deepcopy(self.config['weapons']['laser']))
        hunter_x=25 if case=='close' else 100
        self.enemy=self.entity(1,[hunter_x,-52,0],1400)
        self.enemies=[self.enemy]
        if case=='flank':
            self.enemies.append(self.entity(2,[-45,-39,0],1400))
        self.entities=[self.me]+self.enemies
        self.enemy_nav={e['id']:Navigator(self.world,self.config['mech']) for e in self.enemies}
        for entity,target in [(self.me,self.enemy)]+[(e,self.me) for e in self.enemies]:
            origin=[*entity['pos'][:2],entity['stats']['muzzle_height']]
            point=[*target['pos'][:2],target['stats']['height']/2]
            entity['aim']=lead(origin,point,target['vel'],entity['weapons'][0]['stats']['speed'])
        self.laser_shots=0;self.laser_hits=0;self.laser_damage=0.0
        self.laser_emissions=[];self.blocked_lasers=0
        self.exposure=0.0;self.charged_exposure=0.0
        self.retreat_at=None;self.energy_used=0.0;self.trace=[]
        self.action={};self.growth_collision=False
        # Prior observer position is genuinely below the wall's corner, with
        # direct eye LOS; this earns the published five-second tracking memory.
        hidden=list(self.me['pos']);self.me['pos']=[-12,-52,0];self.t=98.9
        prior=self.observation(-22)
        self.prior_visible=[e['id'] for e in prior['mechs']]
        self.bot.remember(prior)
        self.me['pos']=hidden;self.t=100

    def observation(self,tick):
        # Public vision permits center OR top. Keep this separate from the
        # weapon muzzle; seeing a head above low cover does not permit a beam.
        for enemy in self.enemies:
            top=[*enemy['pos'][:2],enemy['pos'][2]+enemy['stats']['height']*.95]
            if enemy['hp']>0 and self.visible(self.me,top):
                self.seen[enemy['id']]=self.t
        obs=super().observation(tick)
        obs['alive']=16
        return obs

    def move_entity(self,entity,action):
        laser=next((w for w in entity['weapons'] if w and w['kind']=='laser'),None)
        charging=bool(laser and (laser.get('charge',0)>0 or laser.get('_pending',False) or
            (laser.get('cooldown',0)<=0 and action.get('fire',[False,False])[1])))
        original=entity['stats']
        before=entity['energy']
        if charging:
            entity['stats']=dict(original)
            factor=original.get('charge_move_mult',.5)
            entity['stats']['walk_speed']*=factor
            entity['stats']['boost_speed']*=factor
        if (entity['grounded'] and math.hypot(*action.get('move',[0,0]))<1e-6 and
                math.hypot(*entity['vel'][:2])<1e-6):
            action={**action,'boost':False}
        super().move_entity(entity,action)
        entity['stats']=original
        if entity['id']==0:
            self.energy_used+=max(0,before-entity['energy'])

    def laser_release(self,entity,laser,held):
        stats=laser['stats'];yaw,pitch=entity['aim']
        origin=[*entity['pos'][:2],entity['pos'][2]+entity['stats']['muzzle_height']]
        direction=[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
        end=[origin[i]+direction[i]*stats['range'] for i in range(3)]
        fraction=stats['min_frac']+(1-stats['min_frac'])*min(1,held/stats['charge'])
        candidates=[]
        for target in self.entities:
            if target is entity or target['hp']<=0:
                continue
            entry=cylinder_entry(origin,end,target['pos'],target['stats']['radius'],target['stats']['height'])
            if entry is not None:
                candidates.append((entry,target))
        hit=False
        for entry,target in sorted(candidates,key=lambda row:row[0]):
            point=[origin[i]+(end[i]-origin[i])*entry for i in range(3)]
            if not self.world.line_clear(origin,point):
                self.blocked_lasers+=1
                break
            bearing=math.atan2(origin[1]-target['pos'][1],origin[0]-target['pos'][0])
            rear=abs(wrapped(bearing-target['aim'][0]))>math.radians(target['stats']['front_arc_deg'])/2
            damage=stats['damage']*fraction*(target['stats']['rear_mult'] if rear else 1)
            damage*=1-target['stats'].get('armor',0)
            if any(w and w['kind']=='mortar' for w in target['weapons']):
                damage*=1+stats['cookoff']
            target['hp']-=damage;target['_combat']=entity['_combat']=self.t
            if entity['id']==0:
                self.events.append(dict(type='hit',weapon='laser',target=target['id'],amount=damage,rear=rear))
                self.metrics['damage_dealt']+=damage
                self.laser_hits+=1;self.laser_damage+=damage
                if target['hp']<=0:
                    self.events.append(dict(type='kill',target=target['id']))
                    self.metrics['kills']+=1
            elif target['id']==0:
                self.events.append(dict(type='damaged',weapon='laser',by=entity['id'],amount=damage,
                                        bearing=bearing,rear=rear))
                self.metrics['damage_taken']+=damage
            hit=True;break
        if entity['id']==0:
            self.laser_shots+=1
            self.laser_emissions.append(dict(t=self.t-100,charge=held,hit=hit,
                origin=origin,aim=list(entity['aim'])))
        laser.update(charge=0,cooldown=stats['cooldown'],_held=0,_pending=False)

    def weapon(self,entity,action):
        super().weapon(entity,action)
        laser=next((w for w in entity['weapons'] if w and w['kind']=='laser'),None)
        if laser is None:
            return
        laser['cooldown']=max(0,laser.get('cooldown',0)-DT)
        trigger=bool(action.get('fire',[False,False])[1])
        held=laser.get('_held',laser.get('charge',0))
        if held<=0 and laser['cooldown']>0:
            return
        if held>0 and not trigger:
            laser['_pending']=True
        if trigger or held>0 or laser.get('_pending'):
            held+=DT;laser['_held']=held
            laser['charge']=held if self.reported_total_charge else min(laser['stats']['charge'],held)
            if (laser.get('_pending') and held+1e-8>=laser['stats']['min_charge']) or (
                    held+1e-8>=laser['stats']['charge']+laser['stats']['hold_s']):
                self.laser_release(entity,laser,held)

    def run(self):
        action={};released=False
        for tick in range(round(self.seconds/DT)):
            self.t=100+tick*DT
            if tick%2==0:
                obs=self.observation(tick);action=self.bot.act(obs);self.action=action
                planner=getattr(self.bot,'ambush',None)
                self.metrics['ignored_jump_requests']+=bool(action.get('jump'))
                self.trace.append(dict(t=round(self.t-100,3),pos=list(self.me['pos']),
                    hp=self.me['hp'],enemy_hp=self.enemy['hp'],charge=self.me['weapons'][1]['charge'],
                    state=getattr(planner,'state','absent'),reason=getattr(planner,'reason',None),
                    fire=list(action['fire']),move=list(action['move']),boost=action.get('boost',False)))
            actions={0:action}
            actions.update({e['id']:self.enemy_action(e,tick) for e in self.enemies if e['hp']>0})
            for entity in self.entities:
                if entity['hp']>0:
                    self.move_entity(entity,actions[entity['id']]);self.weapon(entity,actions[entity['id']])
            self.projectiles()
            exposed=any(e['hp']>0 and firing_lane(self.world,self.config,self.me['pos'],self.me,e)[0]
                        for e in self.enemies)
            self.exposure+=DT*exposed
            self.charged_exposure+=DT*exposed*(self.me['weapons'][1]['charge']>0)
            released|=self.laser_hits>0
            if released and not exposed and self.retreat_at is None:
                self.retreat_at=self.t-100
            self.growth_collision|=not self.world.body_clear(*self.me['pos'],
                self.me['stats']['radius']-.001,self.me['stats']['height'],0)
            if self.me['hp']<=0 or self.enemy['hp']<=0 or self.growth_collision:
                break
        return dict(player_hp=self.me['hp'],enemy_hp=self.enemy['hp'],
            damage_dealt=self.metrics['damage_dealt'],damage_taken=self.metrics['damage_taken'],
            laser_shots=self.laser_shots,laser_hits=self.laser_hits,laser_damage=self.laser_damage,
            exposure_s=self.exposure,charged_exposure_s=self.charged_exposure,
            retreat_at=self.retreat_at,energy=self.me['energy'],energy_spent=self.energy_used,
            ignored_jumps=self.metrics['ignored_jump_requests'],body_collision=self.growth_collision,
            trace=self.trace,emissions=self.laser_emissions)


class LaserPhysicsTests(unittest.TestCase):
    def test_charging_halves_actual_walk_velocity(self):
        slow=AmbushFeedback();fast=AmbushFeedback()
        slow.me['weapons'][1]['charge']=.4
        for tick in range(10):
            for model in (slow,fast):
                model.move_entity(model.me,dict(move=[-1,0],boost=False,fire=[False,False]))
        self.assertAlmostEqual(abs(slow.me['vel'][0]),5.85,places=4)
        self.assertAlmostEqual(abs(fast.me['vel'][0]),11.7,places=4)

    def test_full_charge_auto_fires_into_wall_without_a_free_hit(self):
        model=AmbushFeedback();laser=model.me['weapons'][1]
        maximum_reported=0;maximum_private=0
        for tick in range(56):
            model.t=100+tick*DT
            model.weapon(model.me,dict(fire=[False,True],reload=False))
            maximum_reported=max(maximum_reported,laser['charge'])
            maximum_private=max(maximum_private,laser.get('_held',0))
        self.assertEqual(model.laser_shots,1)
        self.assertEqual(model.laser_hits,0)
        self.assertEqual(model.enemy['hp'],1400)
        self.assertGreater(laser['cooldown'],0)
        self.assertEqual(laser['charge'],0)
        self.assertGreaterEqual(model.laser_emissions[0]['charge'],2.75-1e-6)
        self.assertAlmostEqual(maximum_reported,.75)
        self.assertGreater(maximum_private,2.5)

    def test_visible_head_above_low_wall_does_not_give_muzzle_a_free_beam(self):
        model=AmbushFeedback()
        model.world=flat_world([rectangle(-3,-45,3,45,top=7.5)])
        model.me['pos']=[-12,0,0];model.enemy['pos']=[100,0,0]
        origin=[-12,0,7];head=[100,0,8.55];center=[100,0,4.5]
        self.assertTrue(model.visible(model.me,head))
        self.assertFalse(model.world.line_clear(origin,center))
        model.me['aim']=lead(origin,center,[0,0,0],252)
        for tick in range(16):
            model.t=100+tick*DT
            model.weapon(model.me,dict(fire=[False,tick<15],reload=False))
        self.assertEqual(model.laser_shots,1)
        self.assertEqual(model.laser_hits,0)
        self.assertEqual(model.enemy['hp'],1400)

    def test_releasing_early_waits_for_minimum_charge(self):
        model=AmbushFeedback()
        for tick in range(3):
            model.t=100+tick*DT
            model.weapon(model.me,dict(fire=[False,tick==0],reload=False))
        self.assertEqual(model.laser_shots,1)
        self.assertAlmostEqual(model.laser_emissions[0]['charge'],.15)


class AmbushFeedbackTests(unittest.TestCase):
    def test_charge_peek_hit_and_physical_retreat(self):
        model=AmbushFeedback()
        self.assertIn(1,model.prior_visible)
        result=model.run()
        self.assertGreater(result['laser_hits'],0)
        self.assertGreaterEqual(result['laser_damage'],315-1e-6)
        self.assertIsNotNone(result['retreat_at'])
        self.assertEqual(result['ignored_jumps'],0)
        self.assertFalse(result['body_collision'])
        self.assertGreater(result['player_hp'],0)

    def test_elapsed_total_charge_reports_also_allow_a_real_peek_and_retreat(self):
        model=AmbushFeedback(reported_total_charge=True)
        result=model.run()
        self.assertGreater(result['laser_hits'],0)
        self.assertIsNotNone(result['retreat_at'])
        self.assertFalse(result['body_collision'])

    def test_close_or_flanked_player_cannot_start_prepared_ambush(self):
        for case in ('close','flank'):
            with self.subTest(case=case):
                model=AmbushFeedback(case,seconds=.2)
                model.run()
                planner=getattr(model.bot,'ambush',None)
                self.assertIsNotNone(planner,'candidate ambush hook was not integrated')
                self.assertIn(planner.state,('idle','cooldown'))


if __name__=='__main__':
    unittest.main()
