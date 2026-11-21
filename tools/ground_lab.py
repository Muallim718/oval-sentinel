"""LIMITED reactive ground-gun scenarios. These are NOT Mech Royale matches.

Uses the project's real Bot, World collision, Navigator, and public config, but
approximates physics/ordering, enemy AI, and visibility. Reports diagnostics only.
"""
import argparse
from array import array
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

DT = .05


def wrapped(a):
    return (a+math.pi) % math.tau-math.pi


def slew(old, wanted, maximum, angular=False):
    delta = wrapped(wanted-old) if angular else wanted-old
    return old+max(-maximum, min(maximum, delta))


def cylinder_entry(a, b, pos, radius, height):
    """First segment fraction intersecting a closed vertical cylinder."""
    dx, dy, dz = [b[i]-a[i] for i in range(3)]
    x, y = a[0]-pos[0], a[1]-pos[1]
    aa, bb, cc = dx*dx+dy*dy, 2*(x*dx+y*dy), x*x+y*y-radius*radius
    if aa < 1e-12:
        if cc > 0:
            return None
        lo, hi = 0.0, 1.0
    else:
        disc = bb*bb-4*aa*cc
        if disc < 0:
            return None
        lo, hi = sorted(((-bb-math.sqrt(disc))/(2*aa),
                         (-bb+math.sqrt(disc))/(2*aa)))
        lo, hi = max(0, lo), min(1, hi)
    if abs(dz) < 1e-12:
        if not pos[2] <= a[2] <= pos[2]+height:
            return None
    else:
        zlo, zhi = sorted(((pos[2]-a[2])/dz, (pos[2]+height-a[2])/dz))
        lo, hi = max(lo, zlo), min(hi, zhi)
    return lo if lo <= hi else None


def lead(origin, target, velocity, speed):
    r = [target[i]-origin[i] for i in range(3)]
    aa = sum(v*v for v in velocity)-speed*speed
    bb, cc = 2*sum(r[i]*velocity[i] for i in range(3)), sum(v*v for v in r)
    disc = bb*bb-4*aa*cc
    roots = [] if disc < 0 else [(-bb-math.sqrt(disc))/(2*aa),
                                (-bb+math.sqrt(disc))/(2*aa)]
    t = min((t for t in roots if t >= 0), default=0)
    p = [target[i]+velocity[i]*t-origin[i] for i in range(3)]
    return [math.atan2(p[1], p[0]), math.atan2(p[2], math.hypot(*p[:2]))]


class Lab:
    def __init__(self, root, scenario, seed, seconds):
        from sentinel.strategy import Bot
        from sentinel.geometry import World, Prism
        from sentinel.navigation import Navigator
        from sentinel.combat import Combat
        with gzip.open(root/'check/stream.jsonl.gz', 'rt', encoding='utf-8') as stream:
            self.hello, self.initial = json.loads(next(stream)), json.loads(next(stream))
        self.hello['map']['dir'] = str(root/'arena')
        self.hello['seed'] = seed
        self.config = self.hello['config']
        self.bot = Bot(self.hello)
        self.entity_rng = {i:random.Random(seed+1009*i) for i in range(3)}
        self.scenario, self.seconds = scenario, seconds
        world = World.__new__(World)
        world.bounds = {'minX':-120,'maxX':120,'minY':-120,'maxY':120}
        world.terrain = {'minX':-125,'minY':-125,'step':1,'nx':251,'ny':251,'scale':.01}
        world.heights = array('h', [0])*(251*251)
        rectangles = [(-3,-45,3,45)] if scenario != 'open_pursuit' else []
        world.prisms = [Prism({'base':0, 'top':20,
                              'ring':[a,b,c,b,c,d,a,d], 'holes':[]})
                        for a,b,c,d in rectangles]
        world.buckets = {}
        for index,p in enumerate(world.prisms):
            a,b,c,d = p.bounds
            for y in range(math.floor(b/world.CELL), math.floor(d/world.CELL)+1):
                for x in range(math.floor(a/world.CELL), math.floor(c/world.CELL)+1):
                    world.buckets.setdefault((x,y), []).append(index)
        self.world = world
        self.bot.world = world
        self.bot.nav = Navigator(world, self.config['mech'])
        self.bot.combat = Combat(world, self.config)
        if hasattr(self.bot, 'cover'):
            from sentinel.cover import CoverPlanner
            self.bot.cover = CoverPlanner(world, self.config)
        if hasattr(self.bot, 'motion'):
            from sentinel.movement import GroundSteering
            self.bot.motion = GroundSteering(world, self.config)
        if hasattr(self.bot, 'altitude'):
            from sentinel.altitude import RoofSanctuary
            self.bot.altitude = RoofSanctuary(world, self.config)
        self.me = self.entity(0, [-55,-50,0], hp=650)
        if scenario == 'open_pursuit':
            enemy_positions = [[30,-50,0]]
        elif scenario == 'corner_recovery':
            self.me['pos'] = [-30,-54,0]
            enemy_positions = [[50,-54,0]]
        elif scenario == 'crossfire_cover':
            self.me['pos'] = [-30,-52,0]
            enemy_positions = [[50,-52,0], [40,55,0]]
        elif scenario == 'quiet_loot':
            self.me['pos'], self.me['hp'] = [-70,0,0], 1400
            enemy_positions = []
        else:
            raise ValueError(scenario)
        self.enemies = [self.entity(i+1, pos, hp=1400) for i,pos in enumerate(enemy_positions)]
        self.entities = [self.me]+self.enemies
        self.enemy_nav = {e['id']:Navigator(world,self.config['mech']) for e in self.enemies}
        self.enemy_waypoints = {}
        self.bullets, self.events, self.seen = [], [], {}
        self.t = 100.0
        self.zone = copy.deepcopy(self.initial['zone'])
        self.zone.update(center=[0,0],radius=117,next_center=[0,0],next_radius=117,
                         shrink_start=500,shrink_end=550,dps=20)
        self.loot = [{'id':5001,'pos':[35,0,0]}] if scenario == 'quiet_loot' else []
        self.metrics = dict(damage_taken=0.0, damage_dealt=0.0, healing=0.0,
                            exposed_s=0.0, shots=0, kills=0, cubes_collected=0,
                            ignored_jump_requests=0, movement_m=0.0,
                            max_decision_ms=0.0)
        self.death_time = None
        self.next_bullet = 1

    def entity(self, ident, pos, hp):
        me = copy.deepcopy(self.initial['self'])
        me.update(id=ident, pos=list(pos), vel=[0,0,0], aim=[0,0], hp=hp,
                  max_hp=1400, energy=100, grounded=True, in_zone=True,
                  cubes=0,upgrades=[])
        gun = copy.deepcopy(me['weapons'][0])
        gun.update(ammo=gun['stats']['mag'],reload=0,cooldown=0)
        me['weapons'] = [gun,None]
        me['_combat'],me['_spent'] = 99.5,99.5
        return me

    def visible(self, observer, position):
        d = math.dist(observer['pos'][:2],position[:2])
        yaw = math.atan2(position[1]-observer['pos'][1],position[0]-observer['pos'][0])
        vision = self.config['vision']
        eye = [*observer['pos'][:2],observer['pos'][2]+observer['stats']['eye_height']]
        return (d <= vision['near_range'] or
                (d <= vision['range'] and abs(wrapped(yaw-observer['aim'][0])) <=
                 math.radians(vision['fov_deg'])/2)) and self.world.line_clear(eye,position)

    def observation(self, tick):
        obs = copy.deepcopy(self.initial)
        enemies = []
        for enemy in self.enemies:
            if enemy['hp'] <= 0:
                continue
            target = [*enemy['pos'][:2],enemy['pos'][2]+enemy['stats']['height']/2]
            if self.visible(self.me,target):
                self.seen[enemy['id']] = self.t
            if self.t-self.seen.get(enemy['id'],-100) <= self.config['vision']['memory_s']:
                enemies.append({k:copy.deepcopy(enemy[k]) for k in
                                ('id','pos','vel','aim','hp','max_hp','cubes')})
                enemies[-1].update(kind='mech',weapons=['gun'],charging=False)
        obs.update(type='obs',t=self.t,tick=tick,alive=1+sum(e['hp']>0 for e in self.enemies),
                   self={k:copy.deepcopy(v) for k,v in self.me.items() if not k.startswith('_')},
                   mechs=enemies, projectiles=[dict(id=b['id'],kind='gun',pos=b['pos'],vel=b['vel'])
                        for b in self.bullets if b['by'] != 0 and self.visible(self.me,b['pos'])],
                   events=self.events,crates=[],cubes=copy.deepcopy(self.loot),pickups=[],
                   drops=[],sounds=[],beams=[],offer=None,zone=copy.deepcopy(self.zone))
        # Keep alive > 2 so these are recovery tests, not the bot's final duel mode.
        obs['alive'] = max(3,obs['alive'])
        self.events = []
        return obs

    def enemy_action(self, enemy, tick):
        target = [*self.me['pos'][:2],self.me['pos'][2]+self.me['stats']['height']/2]
        origin = [*enemy['pos'][:2],enemy['pos'][2]+enemy['stats']['muzzle_height']]
        if tick % 10 == 0 or enemy['id'] not in self.enemy_waypoints:
            self.enemy_waypoints[enemy['id']] = self.enemy_nav[enemy['id']].waypoint(
                enemy['pos'],self.me['pos'][:2],self.t,([0,0],117),[])
        waypoint = self.enemy_waypoints[enemy['id']]
        d = math.dist(enemy['pos'][:2],self.me['pos'][:2])
        can_fire = self.world.line_clear(origin,target)
        move = [waypoint[i]-enemy['pos'][i] for i in range(2)] if d>35 or not can_fire else [0,0]
        length = math.hypot(*move)
        move = [v/(length or 1) for v in move]
        desired = lead(origin,target,self.me['vel'],enemy['weapons'][0]['stats']['speed'])
        # A fixed seeded model of imperfect but competent aim, not house AI.
        desired[0] += math.sin(self.t*2.7+enemy['id'])*.008
        fire = can_fire and d<210
        return dict(move=move,boost=d>65 and enemy['energy']>30,aim=desired,
                    fire=[fire,False],reload=enemy['weapons'][0]['ammo']==0)

    def move_entity(self, entity, action):
        stats = entity['stats']
        move = action.get('move',[0,0])
        norm = max(1,math.hypot(*move))
        boost = bool(action.get('boost')) and entity['energy']>0 and norm>0
        speed = stats['boost_speed'] if boost else stats['walk_speed']
        wanted = [v/norm*speed for v in move]
        dv = [wanted[i]-entity['vel'][i] for i in range(2)]
        change = math.hypot(*dv)
        factor = min(1,stats['ground_accel']*DT/(change or 1))
        entity['vel'] = [entity['vel'][i]+dv[i]*factor for i in range(2)]+[0]
        old = entity['pos']
        proposed = [old[i]+entity['vel'][i]*DT for i in range(2)]+[0]
        proposed[2] = self.world.ground(*proposed[:2])
        kwargs = dict(radius=stats['radius'],height=stats['height'],step=stats['step_up'])
        if not self.world.walk_clear(old,proposed,**kwargs):
            # Approximate wall slide; full authoritative eave/roof physics absent.
            candidates = [[proposed[0],old[1],old[2]], [old[0],proposed[1],old[2]],old]
            proposed = next((p for p in candidates if self.world.walk_clear(old,p,**kwargs)),old)
            entity['vel'] = [(proposed[i]-old[i])/DT for i in range(2)]+[0]
        entity['pos'] = proposed
        if entity['id']==0:
            self.metrics['movement_m'] += math.dist(old,proposed)
        if boost:
            entity['energy'] = max(0,entity['energy']-stats['boost_drain']*DT)
            entity['_spent'] = self.t
        elif self.t-entity['_spent'] >= stats['energy_regen_delay']:
            entity['energy'] = min(entity['max_energy'],entity['energy']+stats['energy_regen']*DT)
        aim = action.get('aim',entity['aim'])
        entity['aim'] = [slew(entity['aim'][0],aim[0],stats['turn_rate']*DT,True),
                         slew(entity['aim'][1],aim[1],stats['pitch_rate']*DT)]
        entity['in_zone'] = math.dist(entity['pos'][:2],[0,0]) < 117
        if not entity['in_zone']:
            entity['hp'] -= self.zone['dps']*DT
            entity['_combat'] = self.t
            if entity['id']==0:
                self.metrics['damage_taken'] += self.zone['dps']*DT
                self.events.append(dict(type='damaged',amount=self.zone['dps']*DT,
                                        weapon='zone',bearing=None,by=None))
        if self.t-entity['_combat'] >= stats['regen_delay'] and entity['in_zone']:
            amount = min(entity['max_hp']-entity['hp'],stats['regen_per_s']*DT)
            entity['hp'] += amount
            if entity['id']==0:
                self.metrics['healing'] += amount

    def weapon(self, entity, action):
        gun = entity['weapons'][0]
        stats = gun['stats']
        gun['cooldown'] = max(-DT,gun['cooldown']-DT)
        if action.get('reload') and gun['reload']<=0 and gun['ammo']<stats['mag']:
            gun['reload'] = stats['reload']
        if gun['reload']>0:
            gun['reload'] = max(0,gun['reload']-DT)
            if gun['reload']<=1e-8:
                gun['reload'],gun['ammo'] = 0,stats['mag']
        if action.get('fire',[False])[0] and gun['cooldown']<=0 and gun['reload']==0 and gun['ammo']>0:
            gun['ammo']-=1
            gun['cooldown']+=stats['cooldown']
            yaw,pitch = entity['aim']
            rng = self.entity_rng[entity['id']]
            yaw += rng.gauss(0,math.radians(stats['spread_deg']))
            pitch += rng.gauss(0,math.radians(stats['spread_deg']))
            origin = [*entity['pos'][:2],entity['pos'][2]+entity['stats']['muzzle_height']]
            velocity = [stats['speed']*math.cos(pitch)*math.cos(yaw),
                        stats['speed']*math.cos(pitch)*math.sin(yaw),stats['speed']*math.sin(pitch)]
            self.bullets.append(dict(id=self.next_bullet,by=entity['id'],pos=origin,
                                     vel=velocity,remaining=stats['range'],damage=stats['damage']))
            self.next_bullet += 1
            if entity['id']==0:
                self.metrics['shots']+=1

    def projectiles(self):
        surviving=[]
        for bullet in self.bullets:
            a=bullet['pos']; b=[a[i]+bullet['vel'][i]*DT for i in range(3)]
            hits=[]
            for target in self.entities:
                if target['id']==bullet['by'] or target['hp']<=0:
                    continue
                if bullet['by'] != 0 and target['id'] != 0:
                    continue  # Pursuers cooperate; they do not damage each other.
                t=cylinder_entry(a,b,target['pos'],target['stats']['radius'],target['stats']['height'])
                if t is not None:
                    hits.append((t,target))
            hit=False
            for fraction,target in sorted(hits,key=lambda x:x[0]):
                p=[a[i]+(b[i]-a[i])*fraction for i in range(3)]
                if not self.world.line_clear(a,p):
                    break
                bearing=math.atan2(-bullet['vel'][1],-bullet['vel'][0])
                rear=abs(wrapped(bearing-target['aim'][0]))>math.radians(target['stats']['front_arc_deg'])/2
                amount=bullet['damage']*(target['stats']['rear_mult'] if rear else 1)*(1-target['stats'].get('armor',0))
                target['hp']-=amount;target['_combat']=self.t
                owner=self.entities[bullet['by']];owner['_combat']=self.t
                if target['id']==0:
                    self.metrics['damage_taken']+=amount
                    self.events.append(dict(type='damaged',amount=amount,weapon='gun',
                                            bearing=bearing,by=bullet['by'],rear=rear))
                elif bullet['by']==0:
                    self.metrics['damage_dealt']+=amount
                    self.events.append(dict(type='hit',target=target['id'],amount=amount,weapon='gun',rear=rear))
                    if target['hp']<=0:
                        self.metrics['kills']+=1
                        self.events.append(dict(type='kill',target=target['id']))
                hit=True;break
            bullet['remaining']-=math.dist(a,b)
            if not hit and bullet['remaining']>0 and self.world.line_clear(a,b):
                bullet['pos']=b;surviving.append(bullet)
        self.bullets=surviving

    def run(self):
        action={}
        for tick in range(int(self.seconds/DT)):
            self.t=100+tick*DT
            if tick%2==0:
                start=time.perf_counter()
                action=self.bot.act(self.observation(tick))
                self.metrics['max_decision_ms']=max(self.metrics['max_decision_ms'],
                    (time.perf_counter()-start)*1000)
                self.metrics['ignored_jump_requests']+=bool(action.get('jump'))
            actions={0:action}
            for enemy in self.enemies:
                if enemy['hp']>0:
                    actions[enemy['id']]=self.enemy_action(enemy,tick)
            for entity in self.entities:
                if entity['hp']>0:
                    self.move_entity(entity,actions[entity['id']])
                    self.weapon(entity,actions[entity['id']])
            self.projectiles()
            if any(e['hp']>0 and self.world.line_clear(
                    [*e['pos'][:2],e['pos'][2]+7],[*self.me['pos'][:2],self.me['pos'][2]+4.5])
                    for e in self.enemies):
                self.metrics['exposed_s']+=DT
            if self.me['hp']<=0:
                self.death_time=tick*DT;break
            if self.loot and math.dist(self.me['pos'],self.loot[0]['pos'])<self.config['cubes']['pickup_radius']:
                self.metrics['cubes_collected']+=1;self.loot=[]
                self.me['cubes']+=1
                break  # Avoid pretending to model cube growth/upgrade offers.
        return dict(scenario=self.scenario,seed=self.hello['seed'],duration_s=round(tick*DT,2),
                    survived=self.death_time is None,death_s=self.death_time,hp=round(max(0,self.me['hp']),2),
                    final_pos=[round(x,2) for x in self.me['pos']],
                    **{k:round(v,3) if isinstance(v,float) else v for k,v in self.metrics.items()})


def self_check():
    assert cylinder_entry([-10,0,5],[10,0,5],[0,0,0],2,9)==.4
    assert cylinder_entry([-10,3,5],[10,3,5],[0,0,0],2,9) is None
    assert cylinder_entry([-10,0,15],[10,0,15],[0,0,0],2,9) is None
    assert abs(wrapped(3.2)+3.083185307179586)<1e-9


def validate_model(root):
    """Invariants that can silently invalidate a cover/recovery comparison."""
    wall=Lab(root,'corner_recovery',11,1)
    wall.me['pos']=[-30,0,0]
    wall.enemies[0]['pos']=[30,0,0]
    wall.bullets=[dict(id=1,by=1,pos=[30,0,5],vel=[-252,0,0],remaining=230,damage=45)]
    hp=wall.me['hp']
    for _ in range(8):
        wall.projectiles()
    assert wall.me['hp']==hp and not wall.bullets,'shot crossed solid cover'
    clear=Lab(root,'open_pursuit',11,1)
    clear.me['pos']=[-30,0,0];clear.me['aim']=[0,0]
    clear.enemies[0]['pos']=[30,0,0]
    clear.bullets=[dict(id=1,by=1,pos=[30,0,5],vel=[-252,0,0],remaining=230,damage=45)]
    hp=clear.me['hp']
    for _ in range(8):
        clear.projectiles()
    assert clear.me['hp']==hp-45,'unobstructed front hit damage incorrect'
    assert clear.me['_combat']==100 and clear.enemies[0]['_combat']==100,'dealing/taking did not reset regen'
    clear.t=104.9;clear.move_entity(clear.me,{})
    assert clear.me['hp']==hp-45,'regenerated before five quiet seconds'
    clear.t=105.1;clear.move_entity(clear.me,{})
    assert clear.me['hp']==hp-45+45*DT,'quiet regeneration rate incorrect'
    clear.me['_combat']=clear.t
    clear.t+=DT;hp=clear.me['hp'];clear.move_entity(clear.me,{})
    assert clear.me['hp']==hp,'dealing/taking failed to interrupt healing'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=25)
    parser.add_argument('--seeds',type=int,nargs='+',default=[11,29])
    parser.add_argument('--scenarios',nargs='+',default=['open_pursuit','corner_recovery','crossfire_cover','quiet_loot'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=args.project_dir.resolve()
    sys.path.insert(0,str(root));self_check();validate_model(root)
    hashes={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'sentinel').glob('*.py'))}
    start=time.perf_counter()
    results=[Lab(root,scenario,seed,args.seconds).run() for scenario in args.scenarios for seed in args.seeds]
    changed=any(hashlib.sha256((root/p).read_bytes()).hexdigest()!=digest
                for p,digest in hashes.items())
    report=dict(model='limited-ground-gun-lab-v2; NOT match or house-bot simulation',
                project=root.name,source_sha256=hashes,model_assertions='passed',
                source_changed_during_run=changed,
                elapsed_s=round(time.perf_counter()-start,2),results=results)
    encoded=json.dumps(report,indent=2)
    if args.output:
        args.output.write_text(encoded+'\n',encoding='utf-8')
    print(encoded)


if __name__=='__main__':
    main()
