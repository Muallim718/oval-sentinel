"""Physical feedback for phase-aware zone decisions after landing on a roof.

Uses the independent 20 Hz AirFeedback model. It is not authoritative physics;
these are controlled zone decisions, without combat or scored-match prediction.
"""
import math
import unittest

from test_bot import fixture,flat_world,rectangle
from test_altitude_feedback import AirFeedback,flight_feedback
from sentinel.altitude import RoofSanctuary
from sentinel.geometry import distance


class AltitudeZoneFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.hello,_=fixture()
        self.world=flat_world([rectangle(-25,-25,25,25,top=25)])
        self.sites=RoofSanctuary(self.world,self.hello['config']).sites
        self.assertTrue(self.sites)
        self.site=self.sites[0]
        self.flight=flight_feedback(self.hello,self.world,self.site,hold_seconds=3)
        self.controller=self.flight['controller']
        # The flight helper isolates one launch. After landing, restore the roof's
        # actual alternative exits so the zone decision can choose a suitable edge.
        self.controller.sites=self.sites
        self.obs=self.flight['obs'];self.me=self.obs['self']
        self.model=self.flight['model'];self.now=self.obs['t']
        self.trace=[]

    def advance(self,circle,seconds,allow_ground_exit=False):
        states=set()
        for decision in range(math.ceil(seconds/.1)):
            self.now+=.1
            self.obs.update(t=self.now,tick=self.obs['tick']+2)
            # `circle` is the controller's forecast, not an instantaneous storm
            # teleport. Keep the current observed circle large during the walk.
            self.obs['zone'].update(next_center=list(circle[0]),next_radius=circle[1],
                                    shrink_start=self.now+1,shrink_end=self.now+15)
            controls=self.controller.update(self.obs,[],circle,allow_start=False)
            states.add(self.controller.phase)
            if controls is None:
                self.assertTrue(allow_ground_exit,'controller abandoned an otherwise supported roof')
                self.assertTrue(self.me['grounded'])
                self.assertLessEqual(self.me['pos'][2],self.world.ground(*self.me['pos'][:2])+1.5)
                self.assertIsNone(self.controller.site)
                return states,True
            self.assertNotIn('approach',controls,'a landed retarget must not restart ground approach')
            for substep in range(2):
                self.model.step(controls,self.now+substep*.05)
                self.assertTrue(self.world.body_clear(*self.me['pos'],
                    self.me['stats']['radius']-.01,self.me['stats']['height'],0))
                if not allow_ground_exit:
                    self.assertTrue(self.me['grounded'],'same-roof retarget became airborne')
                    self.assertAlmostEqual(self.me['pos'][2],self.site['hold'][2],places=4)
            if decision%5==0:
                self.trace.append((self.now,self.controller.phase,tuple(self.me['pos'])))
        return states,False

    def test_safe_roof_hold_ignores_abandoned_ground_launch_outside_25m_circle(self):
        circle=([0,0],25)
        self.assertGreater(distance(self.site['launch'],circle[0]),circle[1])
        self.assertLess(distance(self.me['pos'],circle[0]),2)
        before=list(self.me['pos']);jumps=self.model.jump_count;jets=self.model.jet_steps
        states,left=self.advance(circle,8)
        self.assertFalse(left)
        self.assertEqual(states,{'hold'})
        self.assertEqual(self.controller.phase,'hold')
        self.assertLess(distance(self.me['pos'],before),1.5)
        self.assertEqual(self.model.jump_count,jumps)
        self.assertEqual(self.model.jet_steps,jets)

    def test_already_airborne_flight_finishes_when_only_old_launch_leaves_forecast(self):
        # Begin a real jump with a safe approach forecast, then contract the
        # forecast around the supported landing/hold while the mech is airborne.
        controller=RoofSanctuary(self.world,self.hello['config'])
        controller.sites=[self.site]
        _,obs=fixture();me=obs['self']
        me.update(pos=list(self.site['launch']),vel=[0,0,0],energy=100,hp=1400,
                  grounded=True,in_zone=True)
        obs.update(t=30,tick=600,events=[],mechs=[])
        model=AirFeedback(self.world,me)
        controls=controller.update(obs,[],([0,0],110),allow_start=True)
        self.assertEqual(controller.phase,'ascend')
        self.assertTrue(controls['jump'])
        for substep in range(2):
            model.step(controls,30+substep*.05)
        self.assertFalse(me['grounded'])
        held=False
        for decision in range(140):
            now=30.1+decision*.1;obs.update(t=now,tick=602+decision*2)
            controls=controller.update(obs,[],([0,0],25),allow_start=False)
            self.assertIsNotNone(controls)
            self.assertNotEqual(controller.phase,'exit')
            self.assertNotIn('approach',controls)
            if controller.phase=='hold':
                held=True
                break
            for substep in range(2):
                model.step(controls,now+substep*.05)
                self.assertTrue(self.world.body_clear(*me['pos'],
                    me['stats']['radius']-.01,me['stats']['height'],0))
        self.assertTrue(held,'airborne forecast change prevented a supported roof landing')
        self.assertTrue(me['grounded'])
        self.assertAlmostEqual(me['pos'][2],self.site['hold'][2])
        self.assertEqual(model.jump_count,1)

    def test_shifting_small_circle_retargets_and_physically_walks_on_same_roof(self):
        self.advance(([0,0],25),1)
        old_position=list(self.me['pos'])
        circle=([10,0],5)
        self.assertGreater(distance(old_position,circle[0]),circle[1])
        jumps=self.model.jump_count;jets=self.model.jet_steps
        states,left=self.advance(circle,8)
        self.assertFalse(left)
        self.assertNotIn('exit',states)
        self.assertEqual(self.controller.phase,'hold')
        self.assertLess(distance(self.me['pos'],circle[0]),circle[1])
        self.assertGreater(distance(self.me['pos'],old_position),5)
        target=self.controller.hold_goal
        self.assertIsNotNone(target)
        self.assertLess(distance(target,circle[0]),circle[1])
        self.assertTrue(self.controller.supported(self.site['prism'],target,
                                                  self.me['stats']['radius']+.3))
        self.assertEqual(self.model.jump_count,jumps)
        self.assertEqual(self.model.jet_steps,jets)

    def test_circle_off_roof_requires_physical_exit_before_ground_policy_resumes(self):
        self.advance(([0,0],25),1)
        self.advance(([10,0],5),8)
        circle=([80,0],5)
        states,left=self.advance(circle,16,allow_ground_exit=True)
        self.assertIn('exit',states)
        self.assertTrue(left,'off-roof circle never completed physical descent')
        self.assertTrue(self.me['grounded'])
        self.assertLessEqual(self.me['pos'][2],self.world.ground(*self.me['pos'][:2])+1.5)
        self.assertFalse(self.site['prism'].contains(*self.me['pos'][:2]))


if __name__=='__main__':
    unittest.main()
