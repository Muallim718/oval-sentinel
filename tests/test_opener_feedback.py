"""Opening acquisition through actual movement, gun hits, and pickup receipts.

Limited20Hz ground model. NPC pursuit/aim and crate drops are declared seeded
approximations, not authoritative AI or placement predictions. No accepted hit
or pickup is mocked; all gun rounds intersect their physical target cylinder.
"""
import copy
import math
import random
import sys
import unittest

from test_bot import ROOT,flat_world,rectangle
sys.path.insert(0,str(ROOT/'tools'))
from ground_lab import Lab,DT,lead,cylinder_entry,wrapped
from sentinel.geometry import distance,unit
from sentinel.navigation import Navigator
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering


class OpenerFeedback(Lab):
    def __init__(self,case='floor',seed=11,seconds=13):
        super().__init__(ROOT,'open_pursuit',seed,seconds)
        self.case=case;self.loot_rng=random.Random(seed)
        walls=[rectangle(60,5,65,50)] if case=='pressure' else []
        self.world=flat_world(walls)
        self.bot.world=self.world;self.bot.nav=Navigator(self.world,self.config['mech'])
        self.bot.combat=Combat(self.world,self.config)
        self.bot.cover=CoverPlanner(self.world,self.config)
        self.bot.motion=GroundSteering(self.world,self.config)
        if hasattr(self.bot,'salvage'):
            from sentinel.salvage import KillSalvage
            self.bot.salvage=KillSalvage(self.world,self.config)
        if hasattr(self.bot,'opener'):
            from sentinel.opener import Opener
            self.bot.opener=Opener(self.world,self.config)
        if hasattr(self.bot,'laser_doctrine'):
            from sentinel.laser_doctrine import LaserDoctrine
            self.bot.laser_doctrine=LaserDoctrine(self.world,self.config)
        self.me=self.entity(0,[0,0,0],1400)
        self.me.update(kind='mech',aim=[0,0]);self.me['_combat']=self.me['_spent']=-100
        self.entities=[self.me];self.enemies=[];self.crates=[];self.pickups=[];self.loot=[]
        self.npc_aggro=False;self.npc_home=None;self.npc_clock=0
        self.destroyed=set();self.next_cube=5000;self.next_pickup=8000
        self.first_seen=None;self.acquired_at=None;self.equip_ready_at=None
        self.first_cube=None;self.pressure_seen=None;self.pressure_plans=[]
        self.trace=[];self.energy_spent=0;self.body_collision=False;self.crate_weapon_roll=None
        self.zone.update(shrink_start=500,shrink_end=550)
        if case=='floor':
            # A legal spawn heading aligned with the old scanner's initial phase
            # avoids giving it an accidental immediate random turn toward loot.
            self.me['aim']=[self.bot.phase,0]
            angle=self.bot.phase+math.pi
            self.pickups=[dict(id=8000,kind='laser',pos=[90*math.cos(angle),90*math.sin(angle),0])]
        elif case in ('crate','pressure'):
            self.crates=[dict(id=1000,kind='crate',pos=[45,0,0],hp=300,max_hp=300,
                              stats=dict(radius=1.4,height=2.4),aim=[0,0],vel=[0,0,0])]
            self.entities+=self.crates
            if case=='pressure':
                hunter=self.entity(1,[75,20,0],1400);hunter['kind']='mech'
                hunter['_combat']=hunter['_spent']=-100
                hunter['aim']=lead([75,20,7],[0,0,4.5],[0,0,0],252)
                self.entities.append(hunter);self.enemies.append(hunter)
        elif case=='npc':
            npc=self.entity(100,[25,0,0],350);npc.update(kind='npc',max_hp=350)
            npc['stats'].update(radius=1.8,height=3.5,eye_height=2.5,muzzle_height=2.2)
            self.entities.append(npc);self.enemies.append(npc)
            self.npc_home=list(npc['pos']);self.entity_rng[100]=random.Random(seed+100900)
        else:
            raise ValueError(case)

    def sees(self,item):
        height=item.get('stats',{}).get('height',1)
        return self.visible(self.me,[*item['pos'][:2],item['pos'][2]+height/2]) or self.visible(
            self.me,[*item['pos'][:2],item['pos'][2]+height*.95])

    def observation(self,tick):
        obs=copy.deepcopy(self.initial);visible=[]
        for entity in self.enemies:
            if entity['hp']<=0:
                continue
            if self.sees(entity):
                self.seen[entity['id']]=self.t
            if self.t-self.seen.get(entity['id'],-100)<=self.config['vision']['memory_s']:
                target={k:copy.deepcopy(entity[k]) for k in ('id','kind','pos','vel','aim','hp','max_hp','cubes')}
                target.update(weapons=['gun'] if entity['kind']=='mech' else [],charging=False)
                visible.append(target)
        crates=[{k:copy.deepcopy(c[k]) for k in ('id','pos','hp')}
                for c in self.crates if c['hp']>0 and self.sees(c)]
        pickups=[copy.deepcopy(p) for p in self.pickups if self.sees(p)]
        cubes=[copy.deepcopy(c) for c in self.loot if self.sees(c)]
        if self.case=='floor' and pickups and self.first_seen is None:
            self.first_seen=self.t
        if any(e['kind']=='mech' for e in visible) and self.pressure_seen is None:
            self.pressure_seen=self.t
        obs.update(t=self.t,tick=tick,alive=16,self={k:copy.deepcopy(v) for k,v in self.me.items()
                   if not k.startswith('_')},mechs=visible,crates=crates,pickups=pickups,cubes=cubes,
                   drops=[],events=self.events,offer=None,sounds=[],beams=[],zone=copy.deepcopy(self.zone),
                   projectiles=[dict(id=p['id'],kind=p.get('kind','gun'),pos=p['pos'],vel=p['vel'])
                        for p in self.bullets if p['by']!=0 and self.visible(self.me,p['pos'])])
        self.events=[]
        return obs

    def take_cube(self):
        config=self.config['cubes'];self.me['cubes']+=1
        total=self.me['cubes'];old=self.me['max_hp']
        self.me['max_hp']=1400*(1+config['hp_per_cube']*min(total,config['stat_cap']))
        self.me['hp']+=self.me['max_hp']-old
        for key in ('radius','height','muzzle_height','eye_height'):
            self.me['stats'][key]=self.config['mech'][key]*(1+config['size_per_cube']*total)
        self.events.append(dict(type='pickup',cubes=total))
        if self.first_cube is None:self.first_cube=self.t

    def collect(self,action):
        self.loot=[cube for cube in self.loot if not self.collect_one(cube)]
        chosen=next((p for p in self.pickups if p['id']==action.get('take')),None)
        if chosen and distance(self.me['pos'],chosen['pos'])<=self.config['loot']['pickup_radius'] and \
                abs(self.me['pos'][2]-chosen['pos'][2])<=4 and self.me['weapons'][1] is None:
            kind=chosen['kind'];stats=copy.deepcopy(self.config['weapons'][kind])
            equip=max(self.config['loot']['equip_s'],stats['cooldown'])
            self.me['weapons'][1]=dict(kind=kind,stats=stats,cooldown=equip,charge=0)
            self.events.append(dict(type='took',id=chosen['id'],kind=kind,slot=1))
            self.acquired_at=self.t;self.equip_ready_at=self.t+equip
            self.pickups.remove(chosen)

    def collect_one(self,cube):
        if distance(self.me['pos'],cube['pos'])<=3.5 and abs(self.me['pos'][2]-cube['pos'][2])<=4:
            self.take_cube();return True
        return False

    def damage(self,bullet,target):
        amount=bullet['damage']
        rear=False
        if target['kind']=='mech':
            bearing=math.atan2(-bullet['vel'][1],-bullet['vel'][0])
            rear=abs(wrapped(bearing-target['aim'][0]))>math.pi/2
            amount*=target['stats']['rear_mult'] if rear else 1
            amount*=1-target['stats'].get('armor',0)
        target['hp']-=amount
        if bullet['by']==0:
            self.events.append(dict(type='hit',target=target['id'],amount=amount,weapon='gun',rear=rear))
            self.metrics['damage_dealt']+=amount;self.me['_combat']=self.t
            if target['kind']=='npc':self.npc_aggro=True
        elif target is self.me:
            self.events.append(dict(type='damaged',by=bullet['by'],amount=amount,
                weapon=bullet.get('kind','gun'),bearing=math.atan2(-bullet['vel'][1],-bullet['vel'][0]),rear=rear))
            self.metrics['damage_taken']+=amount;self.me['_combat']=self.t
        if target['hp']<=0 and target['id']not in self.destroyed:
            self.destroyed.add(target['id'])
            count=1 if target['kind']=='crate' else 2 if target['kind']=='npc' else target['cubes']+2
            for _ in range(count):
                self.loot.append(dict(id=self.next_cube,pos=list(target['pos'])));self.next_cube+=1
            if target['kind']=='crate':
                self.crate_weapon_roll=self.loot_rng.random()<self.config['loot']['crate_weapon_chance']
                if self.crate_weapon_roll:
                    self.pickups.append(dict(id=self.next_pickup,kind=self.loot_rng.choice(
                        ['mortar','laser','lightning']),pos=list(target['pos'])))
                    self.next_pickup+=1
            elif target['kind']=='mech' and bullet['by']==0:
                self.events.append(dict(type='kill',target=target['id']))

    def projectiles(self):
        live=[]
        for bullet in self.bullets:
            a=bullet['pos'];b=[a[i]+bullet['vel'][i]*DT for i in range(3)]
            candidates=[]
            for target in self.entities:
                if target['hp']<=0 or target['id']==bullet['by']:continue
                if bullet['by']!=0 and target is not self.me:continue
                entry=cylinder_entry(a,b,target['pos'],target['stats']['radius'],target['stats']['height'])
                if entry is not None:candidates.append((entry,target))
            hit=False
            for entry,target in sorted(candidates,key=lambda row:row[0]):
                point=[a[i]+(b[i]-a[i])*entry for i in range(3)]
                if not self.world.line_clear(a,point):break
                self.damage(bullet,target);hit=True;break
            bullet['remaining']-=math.dist(a,b)
            if not hit and bullet['remaining']>0 and self.world.line_clear(a,b):
                bullet['pos']=b;live.append(bullet)
        self.bullets=live

    def npc_step(self,npc):
        cfg=self.config['npc'];d=distance(npc['pos'],self.me['pos'])
        origin=[*npc['pos'][:2],2.2];target=[*self.me['pos'][:2],self.me['stats']['height']/2]
        los=self.world.line_clear(origin,target)
        if d<=cfg['aggro_range'] and distance(npc['pos'],self.npc_home)<=cfg['leash'] and los:
            self.npc_aggro=True
        if d>cfg['deaggro_range'] or distance(npc['pos'],self.npc_home)>cfg['chase_leash']:
            self.npc_aggro=False
        goal=self.me['pos'] if self.npc_aggro else self.npc_home
        direction=unit(goal[0]-npc['pos'][0],goal[1]-npc['pos'][1])
        move=direction if distance(npc['pos'],goal)>10 else (0,0)
        npc['vel']=[move[0]*cfg['speed'],move[1]*cfg['speed'],0]
        q=[npc['pos'][i]+npc['vel'][i]*DT for i in range(3)]
        if self.world.walk_clear(npc['pos'],q,1.8,3.5,1.2):npc['pos']=q
        self.npc_clock-=DT
        if self.npc_aggro and los and self.npc_clock<=0:
            aim=lead(origin,target,self.me['vel'],cfg['projectile_speed'])
            rng=self.entity_rng[100];yaw=aim[0]+rng.gauss(0,math.radians(cfg['spread_deg']))
            pitch=aim[1]+rng.gauss(0,math.radians(cfg['spread_deg']))
            self.bullets.append(dict(id=self.next_bullet,kind='npc',by=100,pos=origin,
                vel=[90*math.cos(pitch)*math.cos(yaw),90*math.cos(pitch)*math.sin(yaw),90*math.sin(pitch)],
                remaining=90,damage=cfg['damage']))
            self.next_bullet+=1;self.npc_clock+=cfg['cooldown']

    def run(self):
        action={};stop='timeout'
        for tick in range(round(self.seconds/DT)):
            self.t=tick*DT
            if tick%2==0:
                obs=self.observation(tick);action=self.bot.act(obs)
                opener=getattr(self.bot,'opener',None)
                if self.pressure_seen is not None:self.pressure_plans.append(getattr(opener,'plan',None))
                self.trace.append(dict(t=self.t,pos=list(self.me['pos']),hp=self.me['hp'],
                    target=self.bot.combat.locked_id,state=getattr(opener,'state','absent'),
                    reason=getattr(opener,'reason',None),fire=list(action['fire'])))
                self.metrics['ignored_jump_requests']+=bool(action.get('jump'))
            energy=self.me['energy'];super().move_entity(self.me,action)
            self.energy_spent+=max(0,energy-self.me['energy'])
            super().weapon(self.me,action)
            for enemy in self.enemies:
                if enemy['hp']<=0:continue
                if enemy['kind']=='npc':self.npc_step(enemy)
                else:
                    move=[0,-1] if enemy['pos'][1]>-12 else list(unit(
                        self.me['pos'][0]-enemy['pos'][0],self.me['pos'][1]-enemy['pos'][1]))
                    origin=[*enemy['pos'][:2],7];target=[*self.me['pos'][:2],4.5]
                    controls=dict(move=move,boost=True,aim=lead(origin,target,self.me['vel'],252),
                                  fire=[self.world.line_clear(origin,target),False],reload=False)
                    super().move_entity(enemy,controls);super().weapon(enemy,controls)
            self.projectiles();self.collect(action)
            self.body_collision|=not self.world.body_clear(*self.me['pos'],
                self.me['stats']['radius']-.001,self.me['stats']['height'],0)
            if self.me['hp']<=0:stop='death';break
            if self.metrics['ignored_jump_requests'] or self.body_collision:stop='unsupported_motion';break
            if self.case=='floor' and self.acquired_at is not None:stop='equipment';break
            if self.case in ('crate','npc') and self.me['cubes']>0:stop='cube';break
            if self.case=='pressure' and self.pressure_seen is not None and self.t>self.pressure_seen+.3:
                stop='pressure_handoff';break
        return dict(case=self.case,stop=stop,elapsed=self.t,first_seen=self.first_seen,
            acquired_at=self.acquired_at,equip_ready_at=self.equip_ready_at,
            gear=self.me['weapons'][1]['kind'] if self.me['weapons'][1] else None,
            cubes=self.me['cubes'],first_cube=self.first_cube,hp=self.me['hp'],max_hp=self.me['max_hp'],
            damage_taken=self.metrics['damage_taken'],shots=self.metrics['shots'],energy=self.me['energy'],
            energy_spent=self.energy_spent,crate_weapon_roll=self.crate_weapon_roll,
            pressure_seen=self.pressure_seen,accepted_after_pressure=sum(p is not None for p in self.pressure_plans),
            ignored_jumps=self.metrics['ignored_jump_requests'],body_collision=self.body_collision,
            trace=self.trace)


class OpenerFeedbackTests(unittest.TestCase):
    def test_initially_unseen_floor_weapon_is_physically_reached_and_equipped(self):
        result=OpenerFeedback('floor').run()
        self.assertEqual(result['stop'],'equipment')
        self.assertEqual(result['gear'],'laser')
        self.assertLess(result['acquired_at'],8)
        self.assertAlmostEqual(result['equip_ready_at']-result['acquired_at'],1.65)
        self.assertGreater(result['energy'],0)
        self.assertFalse(result['body_collision'])

    def test_crate_death_collection_uses_actual_hits_with_and_without_weapon_roll(self):
        rolls=[]
        for seed in (1,2):
            result=OpenerFeedback('crate',seed).run();rolls.append(result['crate_weapon_roll'])
            self.assertEqual(result['stop'],'cube')
            self.assertEqual(result['cubes'],1)
            self.assertGreaterEqual(result['shots'],7)
            self.assertFalse(result['body_collision'])
        self.assertEqual(rolls,[True,False])

    def test_npc_retaliates_and_drops_actual_two_cube_reward(self):
        result=OpenerFeedback('npc').run()
        self.assertEqual(result['stop'],'cube')
        self.assertEqual(result['cubes'],2)
        self.assertGreaterEqual(result['shots'],8)
        self.assertGreater(result['damage_taken'],0)
        self.assertFalse(result['body_collision'])

    def test_hunter_rounding_wall_interrupts_before_farm_target_dies(self):
        result=OpenerFeedback('pressure',seconds=3).run()
        self.assertIsNotNone(result['pressure_seen'])
        self.assertEqual(result['accepted_after_pressure'],0)
        self.assertEqual(result['cubes'],0)
        self.assertFalse(result['body_collision'])


if __name__=='__main__':
    unittest.main()
