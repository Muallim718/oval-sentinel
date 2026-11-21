"""A ready short finish must survive unrelated weapon-preference scores."""
import copy
import math
import unittest

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat, ExposedSolution
from sentinel.cover import CoverPlanner
from sentinel.finish_target import FinishTarget
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.opener import Opener
from sentinel.reload_arm import ReloadArm
from sentinel.salvage import KillSalvage
from sentinel.strategy import Bot


class FinishTargetTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[0,0,0], vel=[0,0,0], hp=1400, max_hp=1400, energy=100,
                       cubes=0, grounded=True, in_zone=True)
        self.me["weapons"][0].update(ammo=12,reload=0,cooldown=0)
        self.me["weapons"][1] = self.weapon("lightning")
        self.strong = dict(id=1,kind="mech",pos=[30,-10,0],vel=[0,0,0],hp=1400,
            max_hp=1400,cubes=0,weapons=["gun"],aim=[math.atan2(10,-30),0])
        self.weak = dict(id=2,kind="mech",pos=[100,40,0],vel=[0,0,0],hp=90,
            max_hp=1400,cubes=0,weapons=["gun"],aim=[math.atan2(-40,-100),0])
        self.obs.update(t=30,tick=600,alive=14,mechs=[self.strong,self.weak],events=[],
            projectiles=[],crates=[],cubes=[],pickups=[],drops=[],offer=None)
        self.obs["zone"].update(center=[0,0],radius=118,next_center=[0,0],next_radius=118,
            shrink_start=500,shrink_end=550)
        self.me["aim"] = Combat(self.world,self.config).solve(self.me,self.weak,self.me["weapons"][0])[0]
        self.policy = FinishTarget(self.config)

    def weapon(self, kind, **extra):
        return dict(kind=kind,cooldown=0,charge=0,stats=copy.deepcopy(self.config["weapons"][kind]),**extra)

    def choose(self, **kwargs):
        return self.policy.choose(self.obs,self.obs["mechs"],self.world,**kwargs)

    def bot(self):
        b=Bot(self.hello);b.world=self.world
        b.nav=Navigator(self.world,self.config["mech"])
        b.combat=Combat(self.world,self.config)
        b.cover=CoverPlanner(self.world,self.config)
        b.motion=GroundSteering(self.world,self.config)
        b.opener=Opener(self.world,self.config)
        b.salvage=KillSalvage(self.world,self.config)
        b.reload_arm=ReloadArm(self.world,self.config)
        return b

    def test_close_arc_option_cannot_erase_an_already_aligned_loaded_finish(self):
        ordinary=Combat(self.world,self.config)
        self.assertEqual(ordinary.action(self.me,self.obs["mechs"],False,False)[2]["id"],1)
        choice=self.choose()
        self.assertEqual(choice.target["id"],2)
        self.assertEqual(choice.shots,3)
        self.assertLess(choice.seconds,1.25)
        self.assertFalse(choice.force_gun)
        b=self.bot();action=b.act(self.obs)
        self.assertEqual(b.mode,"evade")
        self.assertIsNone(b.duel)
        self.assertEqual(b.combat.locked_id,2)
        self.assertEqual(action["fire"],[True,False])

    def test_armor_and_current_ammo_must_support_the_entire_short_burst(self):
        self.assertAlmostEqual(self.policy.armor_bound,.24)
        self.me["weapons"][0]["ammo"]=2
        self.assertIsNone(self.choose())
        self.me["weapons"][0]["ammo"]=3
        self.assertIsNotNone(self.choose())
        self.weak["hp"]=110
        self.assertIsNone(self.choose())

    def test_cube_bonus_and_rear_bonus_are_not_invented_to_admit_a_finish(self):
        self.me["cubes"]=10
        self.weak["aim"]=[self.me["aim"][0],0]
        self.weak["hp"]=110
        self.assertIsNone(self.choose())

    def test_actual_slew_reload_or_cooldown_can_cancel_the_finish(self):
        self.me["aim"]=[0,0]
        self.assertIsNone(self.choose())
        self.me["aim"]=Combat(self.world,self.config).solve(self.me,self.weak,self.me["weapons"][0])[0]
        self.me["weapons"][0]["reload"]=.1
        self.assertIsNone(self.choose())
        self.me["weapons"][0].update(reload=0,cooldown=.11)
        self.assertIsNone(self.choose())

    def test_unrelated_held_laser_is_never_triggered_off_or_redirected(self):
        self.me["weapons"][1]=self.weapon("laser")
        self.me["weapons"][1]["charge"]=.3
        self.assertIsNone(self.choose())
        self.me["weapons"][1]["charge"]=0
        b=self.bot();action=b.act(self.obs)
        self.assertTrue(b.finish_target.choice.force_gun)
        self.assertEqual(action["fire"],[True,False])

    def test_wall_and_foreground_bodies_veto_a_false_weak_finish(self):
        self.world=flat_world([rectangle(48,15,55,25)])
        self.assertIsNone(self.choose())
        self.world=flat_world()
        self.obs["mechs"].append(dict(self.strong,id=3,pos=[50,20,0],vel=[15,6,0]))
        self.assertIsNone(self.choose())

    def test_a_foreground_body_on_another_height_does_not_block_the_gun(self):
        self.obs["mechs"].append(dict(self.strong,id=3,pos=[50,20,30]))
        self.assertIsNotNone(self.choose())

    def test_partial_surface_remains_available_to_the_ordinary_scheduler(self):
        self.world = flat_world([rectangle(95, 36, 97, 40, top=6.5)])
        gun = self.me["weapons"][0]
        solution = Combat(self.world, self.config).solve(self.me, self.weak, gun)
        self.assertIsInstance(solution, ExposedSolution)
        self.me["aim"] = solution[0]
        self.assertIsNone(self.choose())

    def test_real_repair_retreat_storm_or_opening_preserve_original_ownership(self):
        for kwargs in (dict(retreat=True),dict(repairing=True),dict(forced_weapon="gun")):
            self.assertIsNone(self.choose(**kwargs))
        self.me["in_zone"]=False
        self.assertIsNone(self.choose())

    def test_only_currently_observed_eligible_attackers_can_be_chosen(self):
        self.assertIsNone(self.policy.choose(self.obs,[self.strong],self.world))
        old=copy.deepcopy(self.weak)
        self.obs["mechs"]=[self.strong]
        self.assertIsNone(self.policy.choose(self.obs,[self.strong,old],self.world))

    def test_new_unseen_or_heavy_rear_pressure_cancels_the_optional_override(self):
        for event in (dict(type="damaged",by=3,weapon="gun",amount=45),
                      dict(type="damaged",by=1,weapon="laser",amount=315),
                      dict(type="damaged",by=1,weapon="gun",amount=67.5,rear=True)):
            self.obs["events"]=[event]
            self.assertIsNone(self.choose())
        self.obs["events"]=[dict(type="damaged",by=1,weapon="gun",amount=45)]
        self.assertIsNotNone(self.choose())

    def test_long_travel_fails_without_moving_toward_a_low_hp_target(self):
        self.weak["pos"]=[210,0,0]
        self.me["aim"]=Combat(self.world,self.config).solve(self.me,self.weak,self.me["weapons"][0])[0]
        self.assertIsNone(self.choose())

    def test_short_target_lease_survives_cooldown_without_predicting_a_hit(self):
        first=self.choose()
        self.assertEqual(first.target["id"],2)
        expires=self.policy.until
        self.obs.update(t=30.1,tick=602)
        self.me["weapons"][0].update(ammo=2,cooldown=.14)
        # HP is unchanged; one emitted bullet need not have arrived yet.
        self.assertEqual(self.choose().target["id"],2)
        self.assertEqual(self.policy.until,expires)
        self.obs.update(t=expires,tick=626)
        self.assertIsNone(self.choose())
        self.obs.update(t=expires+.1,tick=628)
        self.me["weapons"][0].update(ammo=12,cooldown=0)
        self.assertIsNone(self.choose())

    def test_live_loss_of_sight_or_reload_ends_a_target_lease(self):
        self.choose()
        self.obs.update(t=30.1,tick=602,mechs=[self.strong])
        self.assertIsNone(self.choose())
        self.assertIsNone(self.policy.target_id)
        self.obs["mechs"]=[self.strong,self.weak]
        self.choose()
        self.me["weapons"][0]["reload"]=1.2
        self.assertIsNone(self.choose())
        self.assertIsNone(self.policy.target_id)


if __name__=="__main__":
    unittest.main()
