"""Paired healthy gun duels with invented opponents, not scored matches.

Change only --project-dir to compare policies against identical scenario settings.
The default suite tests both plausible aim/movement-versus-fire orderings because
the public protocol does not establish the server's exact substep ordering.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--ranges',type=float,nargs='+',default=[50,90,140])
    parser.add_argument('--seeds',type=int,nargs='+',default=[11,29,47])
    parser.add_argument('--styles',nargs='+',choices=['pursuit','kite'],default=['pursuit','kite'])
    parser.add_argument('--fire-order',choices=['before','after','both'],default='both')
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--enemy-cubes',type=int,choices=range(11),default=0)
    args=parser.parse_args();root=args.project_dir.resolve()
    sys.path[:0]=[str(root),str(root/'tools')]
    from ground_lab import Lab,DT,lead,self_check,validate_model
    from sentinel.geometry import unit,distance
    if args.seconds<=0 or args.seconds>60:
        parser.error('--seconds must be greater than zero and at most60')
    if any(r<=0 or r>210 for r in args.ranges):
        parser.error('--ranges must be greater than zero and at most210m')
    self_check();validate_model(root)

    class Duel(Lab):
        def __init__(self,distance_m,seed,style,order):
            super().__init__(root,'open_pursuit',seed,args.seconds)
            self.distance_m,self.style,self.order=distance_m,style,order
            yaw=math.radians(seed*73%360)
            direction=[math.cos(yaw),math.sin(yaw)]
            self.me.update(pos=[-direction[0]*distance_m/2,-direction[1]*distance_m/2,0],
                           hp=1400,vel=[0,0,0],energy=100)
            self.enemies[0].update(pos=[direction[0]*distance_m/2,direction[1]*distance_m/2,0],
                                   hp=1400,vel=[0,0,0],energy=100)
            enemy=self.enemies[0]
            cubes=max(0,args.enemy_cubes);c=self.config['cubes']
            capped=min(cubes,c['stat_cap'])
            size=1+c.get('size_per_cube',.05)*cubes
            enemy['cubes']=cubes
            enemy['hp']=enemy['max_hp']=1400*(1+c['hp_per_cube']*capped)
            enemy['weapons'][0]['stats']['damage']*=1+c['damage_per_cube']*capped
            for key in ('radius','height','muzzle_height','eye_height'):
                enemy['stats'][key]*=size
            for entity,target in ((self.me,self.enemies[0]),(self.enemies[0],self.me)):
                origin=[*entity['pos'][:2],entity['stats']['muzzle_height']]
                point=[*target['pos'][:2],target['stats']['height']/2]
                entity['aim']=lead(origin,point,target['vel'],entity['weapons'][0]['stats']['speed'])
            self.metrics['zone_damage_taken']=0.0
            self.metrics['incoming_projectile_frames']=0
            self.metrics['over_50ms']=0

        def enemy_action(self,enemy,tick):
            toward=unit(self.me['pos'][0]-enemy['pos'][0],self.me['pos'][1]-enemy['pos'][1])
            d=distance(enemy['pos'],self.me['pos'])
            if self.style=='pursuit':
                move=list(toward) if d>35 else [0,0]
                boost=d>65 and enemy['energy']>30
            elif self.style=='kite':
                radial=max(-1,min(1,(d-110)/30))
                # Seeded side and smooth 5.5-second reversals provide lateral
                # movement instead of another stationary/straight pursuit target.
                side=1 if math.sin((self.t-100)/5.5*math.pi+enemy['id'])>=0 else -1
                move=[toward[0]*radial-toward[1]*.9*side,
                      toward[1]*radial+toward[0]*.9*side]
                boost=d<60 and enemy['energy']>40
            else:
                raise ValueError(self.style)
            # Keep the invented opponent inside the same static circle rather
            # than let easy model wins come from a kiter suiciding in the zone.
            center_distance=math.hypot(*enemy['pos'][:2])
            inward=unit(-enemy['pos'][0],-enemy['pos'][1])
            boundary=max(0,(center_distance-75)/15)
            move=[move[i]+inward[i]*boundary*1.5 for i in range(2)]
            norm=max(1,math.hypot(*move));move=[v/norm for v in move]
            origin=[*enemy['pos'][:2],enemy['pos'][2]+enemy['stats']['muzzle_height']]
            target=[*self.me['pos'][:2],self.me['pos'][2]+self.me['stats']['height']/2]
            aim=lead(origin,target,self.me['vel'],enemy['weapons'][0]['stats']['speed'])
            aim[0]+=math.sin(self.t*2.7+enemy['id'])*.008
            return dict(move=move,boost=boost,aim=aim,
                        fire=[self.world.line_clear(origin,target) and d<210,False],
                        reload=enemy['weapons'][0]['ammo']==0)

        def run(self):
            decision_times=[];outcome='timeout';action={}
            for tick in range(int(self.seconds/DT)):
                self.t=100+tick*DT
                if tick%2==0:
                    observation=self.observation(tick);observation['alive']=16
                    self.metrics['incoming_projectile_frames']+=bool(observation['projectiles'])
                    self.metrics['zone_damage_taken']+=sum(e['amount'] for e in observation['events']
                        if e['type']=='damaged' and e.get('weapon')=='zone')
                    start=time.perf_counter_ns();action=self.bot.act(observation)
                    elapsed=(time.perf_counter_ns()-start)/1e6;decision_times.append(elapsed)
                    self.metrics['max_decision_ms']=max(self.metrics['max_decision_ms'],elapsed)
                    self.metrics['over_50ms']+=elapsed>50
                    self.metrics['ignored_jump_requests']+=bool(action.get('jump'))
                actions={0:action,1:self.enemy_action(self.enemies[0],tick)}
                for entity in self.entities:
                    if entity['hp']<=0:
                        continue
                    old_position=list(entity['pos']);old_aim=list(entity['aim'])
                    self.move_entity(entity,actions[entity['id']])
                    if self.order=='before':
                        position,aim=entity['pos'],entity['aim']
                        entity['pos'],entity['aim']=old_position,old_aim
                        self.weapon(entity,actions[entity['id']])
                        entity['pos'],entity['aim']=position,aim
                    else:
                        self.weapon(entity,actions[entity['id']])
                self.projectiles()
                if self.me['hp']<=0 or self.enemies[0]['hp']<=0:
                    outcome=('mutual' if self.me['hp']<=0 and self.enemies[0]['hp']<=0
                             else 'lost' if self.me['hp']<=0 else 'won')
                    break
            return dict(initial_range=self.distance_m,seed=self.hello['seed'],style=self.style,
                        enemy_cubes=args.enemy_cubes,
                        fire_order=self.order,outcome=outcome,elapsed_s=round(tick*DT,3),
                        self_hp=round(max(0,self.me['hp']),3),
                        enemy_hp=round(max(0,self.enemies[0]['hp']),3),
                        final_range=round(distance(self.me['pos'],self.enemies[0]['pos']),3),
                        median_decision_ms=round(statistics.median(decision_times),4),
                        **{k:round(v,4) if isinstance(v,float) else v for k,v in self.metrics.items()})

    source={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'sentinel').glob('*.py'))}
    orders=['before','after'] if args.fire_order=='both' else [args.fire_order]
    start=time.perf_counter()
    results=[Duel(r,seed,style,order).run() for order in orders for style in args.styles
             for r in args.ranges for seed in args.seeds]
    elapsed=time.perf_counter()-start
    groups=[]
    for order in orders:
        for style in args.styles:
            rows=[r for r in results if r['fire_order']==order and r['style']==style]
            groups.append(dict(fire_order=order,style=style,cases=len(rows),
                               wins=sum(r['outcome']=='won' for r in rows),
                               losses=sum(r['outcome']=='lost' for r in rows),
                               timeouts=sum(r['outcome']=='timeout' for r in rows),
                               mean_damage_dealt=round(statistics.mean(r['damage_dealt'] for r in rows),3),
                               mean_damage_taken=round(statistics.mean(r['damage_taken'] for r in rows),3),
                               mean_self_hp=round(statistics.mean(r['self_hp'] for r in rows),3),
                               zone_damage_taken=sum(r['zone_damage_taken'] for r in rows),
                               ignored_jumps=sum(r['ignored_jump_requests'] for r in rows)))
    report=dict(model='healthy-ground-gun-duel-v1; invented opponents, NOT matches',
                project=root.name,source_sha256=source,elapsed_real_s=round(elapsed,3),
                enemy_cubes=args.enemy_cubes,
                source_changed_during_run=any(hashlib.sha256((root/p).read_bytes()).hexdigest()!=digest
                                             for p,digest in source.items()),
                groups=groups,results=results)
    if args.output:
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','results')},indent=2))


if __name__=='__main__':
    main()
