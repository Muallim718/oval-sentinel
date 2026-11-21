"""A short real-projectile finish after plausible observed trade history.

History seeds public hit/damage/ammo observations, not forced action flags. After
t=100 all positions, ammunition, shots, hits, and health evolve through the 20 Hz
ground-gun model. This is not authoritative physics or a match score predictor.
"""
import copy
from pathlib import Path
import sys
import unittest

from test_bot import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from ground_lab import Lab,DT,lead
from sentinel.geometry import distance


class CommitmentFeedback(Lab):
    def __init__(self):
        super().__init__(ROOT,'open_pursuit',11,2.3)
        self.me.update(pos=[-37.5,0,0],vel=[0,0,0],hp=725,energy=100)
        self.enemy=self.enemies[0]
        self.enemy.update(pos=[37.5,0,0],vel=[0,0,0],hp=225)
        # A real but unobservable enemy reload is one plausible reason recent
        # favorable hits create a brief finish window. The policy never sees its
        # ammo/reload fields: public enemy observations contain only weapon kinds.
        self.enemy['weapons'][0].update(ammo=0,reload=2.4)
        self.me['weapons'][0].update(ammo=8,reload=0,cooldown=0)
        for entity,target in ((self.me,self.enemy),(self.enemy,self.me)):
            origin=[*entity['pos'][:2],entity['stats']['muzzle_height']]
            point=[*target['pos'][:2],target['stats']['height']/2]
            entity['aim']=lead(origin,point,target['vel'],entity['weapons'][0]['stats']['speed'])
        self.prime_history()
        self.trace=[]
        self.action={}
        self._staged=False

    def prime_history(self):
        # Four successful shots fired at98.3/98.6/98.9/99.2, each observed hitting
        # ~0.30s later at75m. Three45HP incoming hits end at98.7. At100, ordinary
        # return fire has expired for1.3s, but own last confirmed hit is only0.5s
        # old. HP decreases405→225 and860→725; ammo12→8 is consistent with shots.
        frames=[(98.0,860,405,12,[]),
                (98.2,815,405,12,[dict(type='damaged',amount=45,weapon='gun',by=1,bearing=0)]),
                (98.3,815,405,11,[]),
                (98.45,770,405,11,[dict(type='damaged',amount=45,weapon='gun',by=1,bearing=0)]),
                (98.6,770,360,10,[dict(type='hit',target=1,amount=45,weapon='gun')]),
                (98.7,725,360,10,[dict(type='damaged',amount=45,weapon='gun',by=1,bearing=0)]),
                (98.9,725,315,9,[dict(type='hit',target=1,amount=45,weapon='gun')]),
                (99.2,725,270,8,[dict(type='hit',target=1,amount=45,weapon='gun')]),
                (99.5,725,225,8,[dict(type='hit',target=1,amount=45,weapon='gun')])]
        for index,(now,hp,enemy_hp,ammo,events) in enumerate(frames):
            obs=copy.deepcopy(self.initial)
            me=copy.deepcopy(self.me);me['hp']=hp;me['weapons'][0]['ammo']=ammo
            enemy={k:copy.deepcopy(self.enemy[k]) for k in
                   ('id','pos','vel','aim','hp','max_hp','cubes')}
            enemy.update(kind='mech',hp=enemy_hp,weapons=['gun'],charging=False)
            obs.update(t=now,tick=1960+index,self=me,mechs=[enemy],events=events,
                       projectiles=[],crates=[],cubes=[],pickups=[],drops=[],beams=[],sounds=[])
            self.bot.remember(obs)
            if hasattr(self.bot,'finish'):
                self.bot.finish.update(obs)
        self.me['_combat']=self.enemy['_combat']=99.5

    def stage_hazard(self,hazard):
        if hazard=='second':
            enemy=self.entity(2,[20,60,0],1400)
            target=[*self.me['pos'][:2],self.me['stats']['height']/2]
            enemy['aim']=lead([*enemy['pos'][:2],enemy['stats']['muzzle_height']],
                              target,self.me['vel'],enemy['weapons'][0]['stats']['speed'])
            self.entities.append(enemy);self.enemies.append(enemy)
            self.enemy_nav[2]=type(self.bot.nav)(self.world,self.config['mech'])
        elif hazard=='zone':
            self.zone.update(next_center=[60,0],next_radius=35,
                             shrink_start=100,shrink_end=102)
        else:
            raise ValueError(hazard)

    def step_decision(self,decision,hazard=None):
        tick=decision*2;self.t=100+decision*.1
        if hazard and not self._staged:
            self.stage_hazard(hazard);self._staged=True
        obs=self.observation(tick);obs['alive']=16
        action=self.bot.act(obs);self.action=action
        commitment=getattr(self.bot,'finish',None)
        self.trace.append(dict(t=round(self.t-100,3),hp=self.me['hp'],enemy_hp=self.enemy['hp'],
            ammo=self.me['weapons'][0]['ammo'],fire=action['fire'][0],mode=self.bot.mode,
            target=getattr(commitment,'target_id',None),
            horizon=getattr(commitment,'horizon',None),reason=getattr(commitment,'reason',None)))
        for substep in range(2):
            self.t=100+decision*.1+substep*DT
            actions={0:action}
            actions.update({e['id']:self.enemy_action(e,tick+substep)
                            for e in self.enemies if e['hp']>0})
            for entity in self.entities:
                if entity['hp']>0:
                    self.move_entity(entity,actions[entity['id']])
                    self.weapon(entity,actions[entity['id']])
            self.projectiles()
        return obs,action

    def run(self):
        for decision in range(23):
            self.step_decision(decision)
            if self.me['hp']<=0 or self.enemy['hp']<=0:
                break
        return dict(enemy_hp=self.enemy['hp'],self_hp=self.me['hp'],
                    killed=self.enemy['hp']<=0,elapsed=self.t-100,
                    shots=self.metrics['shots'],damage_dealt=self.metrics['damage_dealt'],
                    damage_taken=self.metrics['damage_taken'],ammo=self.me['weapons'][0]['ammo'],
                    trace=self.trace)


class CommitmentFeedbackTests(unittest.TestCase):
    def test_favorable_short_finish_uses_real_projectiles_after_return_fire_expired(self):
        model=CommitmentFeedback()
        self.assertGreater(100-model.bot.last_weapon_damage,1)
        self.assertTrue(model.enemy['hp']>170)  # Baseline's existing finish exception does not apply.
        result=model.run()
        self.assertTrue(result['killed'])
        self.assertLess(result['elapsed'],2)
        self.assertGreaterEqual(result['shots'],5)
        self.assertGreaterEqual(result['damage_dealt'],225)
        self.assertGreater(result['self_hp'],0)
        self.assertEqual(model.metrics['ignored_jump_requests'],0)

    def test_second_hunter_or_urgent_zone_immediately_releases_commitment(self):
        for hazard in ('second','zone'):
            with self.subTest(hazard=hazard):
                model=CommitmentFeedback()
                _,initial=model.step_decision(0)
                self.assertTrue(initial['fire'][0])
                self.assertEqual(model.bot.finish.target_id,1)
                self.assertGreater(len(model.bullets),0)  # First real bullet is still in flight.
                observed,action=model.step_decision(1,hazard)
                if hazard=='second':
                    self.assertIn(2,[e['id'] for e in observed['mechs']])
                self.assertIsNone(model.bot.finish.target_id)
                self.assertNotEqual(model.bot.mode,'fight')
                self.assertFalse(action['fire'][0])
                self.assertTrue(model.me['grounded'])


if __name__=='__main__':
    unittest.main()
