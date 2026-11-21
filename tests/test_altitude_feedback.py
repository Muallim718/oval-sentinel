"""Independent, limited 20 Hz flight feedback for the public-roof controller.

This is not authoritative physics. It resolves full-body ceiling contacts and
overlapping roof-edge support; it does not grant free jumps or silently ignore
jet requests. Exact server eave push-out and body pushing are not reproduced.
"""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.geometry import World, distance, unit
from sentinel.movement import GroundSteering


class AirFeedback:
    DT = .05

    def __init__(self, world, me):
        self.world, self.me = world, me
        self.last_spent = -100
        self.jump_count = 0
        self.jet_steps = 0
        self.ceiling_contacts = 0
        self.wall_contacts = 0
        self.landings = 0
        self.edge_landings = 0
        self.spent = 0.0
        self.regenerated = 0.0
        self.min_energy = me['energy']

    @staticmethod
    def nearest_edge(prism, point):
        best = None
        for a,b in prism.all_edges:
            dx,dy = b[0]-a[0],b[1]-a[1]
            t = max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
            q = (a[0]+dx*t,a[1]+dy*t)
            d = distance(point,q)
            if best is None or d < best[0]:
                best = d,q
        return best[1]

    def step(self, action, now):
        me,world,dt = self.me,self.world,self.DT
        s=me['stats']; old=list(me['pos']); old_grounded=me['grounded']
        if action.get('jump') and me['grounded']:
            me['vel'][2]=s['jump_speed'];me['grounded']=False
            self.jump_count+=1
        move=action.get('move',[0,0]);norm=max(1,math.hypot(*move))
        move=[v/norm for v in move]
        boost=bool(action.get('boost')) and me['energy']>0
        jet=boost and not me['grounded']
        sprint=boost and me['grounded'] and math.hypot(*move)>1e-6
        speed=s['boost_speed'] if sprint else s['walk_speed']
        dv=[move[i]*speed-me['vel'][i] for i in range(2)]
        change=math.hypot(*dv)
        accel=s['ground_accel'] if me['grounded'] else s['air_accel']
        fraction=min(1,accel*dt/(change or 1))
        for i in range(2):
            me['vel'][i]+=dv[i]*fraction
        if not me['grounded']:
            me['vel'][2]+=((s['jet_accel'] if jet else 0)-s['gravity'])*dt
            if jet:
                me['vel'][2]=min(s['max_rise_speed'],me['vel'][2])
                self.jet_steps+=1
        else:
            me['vel'][2]=0
        q=[old[i]+me['vel'][i]*dt for i in range(3)]

        # Sweep the head against all overlapping undersides, rather than allowing
        # vertical motion through a slab just because XY did not change.
        if q[2]>old[2]:
            ceilings=[p.base for p in world.nearby(*old[:2],s['radius'])
                      if p.overlaps(*old[:2],s['radius']) and
                      old[2]+s['height']<=p.base+1e-7 and
                      q[2]+s['height']>p.base]
            if ceilings:
                q[2]=min(ceilings)-s['height']
                me['vel'][2]=0
                self.ceiling_contacts+=1

        # Resolve horizontal motion at the higher endpoint, then land if a roof
        # top is crossed while descending. This avoids entering the wall below
        # a roof before the separate vertical support check.
        collision_z=max(old[2],q[2])
        if not world.body_clear(q[0],q[1],collision_z,s['radius'],s['height'],0):
            choices=[[q[0],old[1],q[2]],[old[0],q[1],q[2]],[old[0],old[1],q[2]]]
            valid=[p for p in choices if world.body_clear(
                p[0],p[1],collision_z,s['radius'],s['height'],0)]
            selected=max(valid,key=lambda p:distance(old,p)) if valid else choices[-1]
            q[0],q[1]=selected[:2]
            me['vel'][0],me['vel'][1]=(q[0]-old[0])/dt,(q[1]-old[1])/dt
            self.wall_contacts+=1

        support=world.ground(*q[:2]); edge_prism=None
        for prism in world.nearby(*q[:2],s['radius']):
            if (prism.top<=old[2]+1e-5 and prism.top>=support and
                    prism.overlaps(*q[:2],s['radius'])):
                support=prism.top
                edge_prism=prism if not prism.contains(*q[:2]) else None
        if me['vel'][2]<=0 and q[2]<=support+1e-6:
            q[2],me['vel'][2],me['grounded']=support,0,True
            if not old_grounded:
                self.landings+=1
                self.edge_landings+=edge_prism is not None
            if edge_prism is not None:
                edge=self.nearest_edge(edge_prism,q)
                outward=unit(q[0]-edge[0],q[1]-edge[1])
                # Published roof-edge support slides outward unless movement is
                # into the roof. Exact server resolution is not available.
                if move[0]*outward[0]+move[1]*outward[1]>=-1e-5:
                    slide=[q[0]+outward[0]*.6,q[1]+outward[1]*.6,q[2]]
                    if world.body_clear(*slide,s['radius'],s['height'],0):
                        q=slide
        else:
            me['grounded']=False
        me['pos']=q
        if jet or sprint:
            amount=min(me['energy'],s['jet_drain' if jet else 'boost_drain']*dt)
            me['energy']-=amount;self.spent+=amount;self.last_spent=now
        elif now-self.last_spent>=s['energy_regen_delay']:
            amount=min(me['max_energy']-me['energy'],s['energy_regen']*dt)
            me['energy']+=amount;self.regenerated+=amount
        self.min_energy=min(self.min_energy,me['energy'])


def flight_feedback(hello, world, site, approach_distance=8, hold_seconds=3, trace_sink=None):
    from sentinel.altitude import RoofSanctuary
    h,obs=copy.deepcopy(hello),fixture()[1]
    controller=RoofSanctuary(world,h['config'])
    controller.sites=[site]
    me=obs['self'];s=me['stats']
    away=unit(site['launch'][0]-site['landing'][0],site['launch'][1]-site['landing'][1])
    start=[site['launch'][0]+away[0]*approach_distance,
           site['launch'][1]+away[1]*approach_distance,site['launch'][2]]
    start[2]=world.ground(*start[:2])
    if not world.body_clear(*start,s['radius'],s['height'],0) or not world.walk_clear(
            start,site['launch'],s['radius'],s['height'],s['step_up']):
        start=list(site['launch'])
    me.update(pos=start,vel=[0,0,0],energy=100,hp=1400,grounded=True)
    obs.update(t=20,tick=400,mechs=[],events=[],projectiles=[],crates=[],cubes=[],
               pickups=[],drops=[],sounds=[],beams=[],offer=None,alive=16)
    center=list(site['launch'][:2]);circle=(center,110)
    obs['zone'].update(center=center,radius=110,next_center=center,next_radius=110,
                       shrink_start=500,shrink_end=550)
    model=AirFeedback(world,me);motion=GroundSteering(world,h['config'])
    phases=set();first_hold=None;rows=[] if trace_sink is None else trace_sink
    for decision in range(250):
        now=20+decision*.1;obs.update(t=now,tick=400+2*decision)
        controls=controller.update(obs,[],circle,allow_start=True)
        if controller.phase:
            phases.add(controller.phase)
        if controls is None:
            raise AssertionError(f'controller abandoned at {me["pos"]}, phase={controller.phase}, reason={controller.reason}')
        if 'approach' in controls:
            move,boost=motion.choose(obs,controls['approach'],[],'loot',65,False,
                                     sprinting=False,cover=False,circle=circle)
            controls=dict(move=move,boost=boost,jump=False)
        if decision%5==0:
            rows.append(dict(t=round(now-20,2),phase=controller.phase,
                             pos=[round(v,3) for v in me['pos']],
                             vel=[round(v,3) for v in me['vel']],energy=round(me['energy'],3),
                             grounded=me['grounded']))
        if controller.phase=='hold':
            if first_hold is None:
                first_hold=now
            if now-first_hold>=hold_seconds:
                return dict(me=me,model=model,controller=controller,phases=phases,
                            elapsed=now-20,trace=rows,obs=obs,circle=circle,
                            approach_distance=distance(start,site['launch']))
        for substep in range(2):
            model.step(controls,now+substep*.05)
        if not world.body_clear(*me['pos'],s['radius']-.01,s['height'],0):
            raise AssertionError(f'body intersected a solid at {me["pos"]}')
    raise AssertionError(f'failed to land and hold: {me["pos"]}, phase={controller.phase}')


class AirPhysicsInvariants(unittest.TestCase):
    def setUp(self):
        self.h,self.o=fixture();self.me=self.o['self']
        self.me.update(pos=[-50,0,0],vel=[0,0,0],energy=100,grounded=True)

    def test_jump_is_physical_and_jet_spends_energy(self):
        model=AirFeedback(flat_world(),self.me)
        model.step(dict(move=[0,0],jump=True,boost=True),0)
        self.assertEqual(model.jump_count,1)
        self.assertFalse(self.me['grounded'])
        self.assertGreater(self.me['pos'][2],0)
        self.assertAlmostEqual(self.me['energy'],100-self.me['stats']['jet_drain']*.05)
        self.assertEqual(model.jet_steps,1)

    def test_gravity_lands_an_unpowered_jump(self):
        model=AirFeedback(flat_world(),self.me)
        for tick in range(60):
            model.step(dict(move=[0,0],jump=tick==0,boost=False),tick*.05)
        self.assertTrue(self.me['grounded'])
        self.assertEqual(self.me['pos'][2],0)
        self.assertEqual(model.jump_count,1)
        self.assertEqual(model.jet_steps,0)
        self.assertEqual(self.me['energy'],100)

    def test_ceiling_stops_whole_body_and_still_costs_jet_energy(self):
        world=flat_world([rectangle(-80,-30,-20,30,base=12,top=14)])
        model=AirFeedback(world,self.me)
        for tick in range(40):
            model.step(dict(move=[0,0],jump=tick==0,boost=True),tick*.05)
        self.assertLessEqual(self.me['pos'][2]+self.me['stats']['height'],12+1e-6)
        self.assertGreater(model.ceiling_contacts,0)
        self.assertLess(self.me['energy'],75)
        self.assertFalse(self.me['grounded'])

    def test_roof_edge_support_does_not_require_center_inside(self):
        world=flat_world([rectangle(-20,-20,20,20,top=12)])
        self.me.update(pos=[-21,0,12.1],vel=[0,0,-3],grounded=False)
        model=AirFeedback(world,self.me)
        model.step(dict(move=[1,0],boost=False,jump=False),0)
        self.assertTrue(self.me['grounded'])
        self.assertAlmostEqual(self.me['pos'][2],12)
        self.assertEqual(model.edge_landings,1)
        self.assertFalse(world.prisms[0].contains(*self.me['pos'][:2]))

    def test_wall_blocks_horizontal_air_motion(self):
        world=flat_world([rectangle(-10,-20,10,20,top=25)])
        self.me.update(pos=[-13,0,5],vel=[10,0,0],grounded=False)
        model=AirFeedback(world,self.me)
        for tick in range(8):
            model.step(dict(move=[1,0],boost=True,jump=False),tick*.05)
        self.assertLess(self.me['pos'][0],-12.4)
        self.assertGreater(model.wall_contacts,0)

    def test_idle_roof_edge_slides_off_instead_of_granting_permanent_hover(self):
        world=flat_world([rectangle(-20,-20,20,20,top=12)])
        self.me.update(pos=[-21,0,12],vel=[0,0,0],grounded=True)
        model=AirFeedback(world,self.me)
        for tick in range(70):
            model.step(dict(move=[0,0],boost=False,jump=False),tick*.05)
        self.assertTrue(self.me['grounded'])
        self.assertAlmostEqual(self.me['pos'][2],0)
        self.assertLess(self.me['pos'][0],-22.5)
        self.assertEqual(model.jet_steps,0)


class AltitudeFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.h,self.o=fixture()

    def assert_flight(self,world,site):
        result=flight_feedback(self.h,world,site)
        me,model=result['me'],result['model']
        self.assertTrue(me['grounded'])
        self.assertAlmostEqual(me['pos'][2],site['hold'][2],places=3)
        self.assertLess(distance(me['pos'],site['hold']),3.5)
        self.assertGreater(model.jump_count,0)
        self.assertGreater(model.jet_steps,0)
        self.assertGreater(model.min_energy,0)
        self.assertAlmostEqual(me['energy'],100-model.spent+model.regenerated,places=5)
        expected={'ascend','cross','land','settle','hold'}
        if result['approach_distance']>2.3:
            expected.add('approach')
        self.assertTrue(expected<=result['phases'],result['phases'])
        return result

    def test_12_25_40_meter_roofs_with_air_acceleration_and_energy(self):
        from sentinel.altitude import RoofSanctuary
        for top in (12,25,40):
            with self.subTest(top=top):
                world=flat_world([rectangle(-25,-25,25,25,top=top)])
                sites=RoofSanctuary(world,self.h['config']).sites
                self.assertTrue(sites)
                self.assert_flight(world,sites[0])

    def test_four_varied_public_map_roofs(self):
        from sentinel.altitude import RoofSanctuary
        world=World(self.h['map']['dir'])
        sites=RoofSanctuary(world,self.h['config']).sites
        distinct=[];seen=set()
        for site in sorted(sites,key=lambda x:x['hold'][2]-x['launch'][2]):
            key=id(site['prism'])
            if key not in seen:
                seen.add(key);distinct.append(site)
        self.assertGreaterEqual(len(distinct),4)
        for i in (0,len(distinct)//3,2*len(distinct)//3,len(distinct)-1):
            with self.subTest(site=i,rise=distinct[i]['hold'][2]-distinct[i]['launch'][2]):
                self.assert_flight(world,distinct[i])

    def test_completed_roof_hold_stays_healthy_and_grounded(self):
        from sentinel.altitude import RoofSanctuary
        world=flat_world([rectangle(-25,-25,25,25,top=25)])
        site=RoofSanctuary(world,self.h['config']).sites[0]
        result=flight_feedback(self.h,world,site,hold_seconds=8)
        self.assertEqual(result['controller'].phase,'hold')
        self.assertTrue(result['me']['grounded'])
        self.assertGreater(result['me']['energy'],90)

    def test_zone_change_releases_roof_hold(self):
        from sentinel.altitude import RoofSanctuary
        world=flat_world([rectangle(-25,-25,25,25,top=12)])
        site=RoofSanctuary(world,self.h['config']).sites[0]
        result=flight_feedback(self.h,world,site)
        obs=result['obs'];controller=result['controller'];model=result['model']
        start=obs['t'];left_roof=False
        for decision in range(150):
            now=start+(decision+1)*.1
            obs.update(t=now,tick=obs['tick']+2)
            response=controller.update(obs,[],([0,-75],55),allow_start=False)
            self.assertNotEqual(controller.phase,'hold')
            if response is None:
                self.assertTrue(obs['self']['grounded'])
                self.assertLessEqual(obs['self']['pos'][2],
                                     world.ground(*obs['self']['pos'][:2])+1.5)
                self.assertIsNone(controller.site)
                left_roof=True
                break
            self.assertNotIn('approach',response)
            for substep in range(2):
                model.step(response,now+substep*.05)
        self.assertTrue(left_roof,'zone exit never reached the ground')


if __name__=='__main__':
    unittest.main()
