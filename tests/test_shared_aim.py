"""Gun/laser torso coordination, isolated from the movement policy."""
import copy
import unittest
from test_bot import fixture
from sentinel.combat import Combat
from sentinel.geometry import angle_error
from tools.weapon_feedback import OpenWorld, simulate


class SharedAimTests(unittest.TestCase):
    def setUp(self):
        self.h,self.o = fixture()
        self.me = self.o["self"]
        self.me.update(pos=[0,0,0],aim=[0,0])
        self.gun = self.me["weapons"][0]
        self.laser = {"kind":"laser","cooldown":0,"charge":0,
                      "stats":copy.deepcopy(self.h["config"]["weapons"]["laser"])}
        self.me["weapons"][1] = self.laser
        self.target = {"id":1,"kind":"mech","pos":[120,0,0],"vel":[0,12,0],
                       "hp":1400,"max_hp":1400}
        self.combat = Combat(OpenWorld(),self.h["config"])

    def test_partial_charge_uses_gun_lead_and_fires_both_triggers(self):
        self.laser["charge"] = .3
        gun_aim = self.combat.solve(self.me,self.target,self.gun)[0]
        self.me["aim"] = gun_aim
        aim,fire,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertAlmostEqual(angle_error(aim[0],gun_aim[0]),0)
        self.assertEqual(fire,[True,True])

    def test_charge_can_start_while_commanding_projectile_lead(self):
        gun_aim = self.combat.solve(self.me,self.target,self.gun)[0]
        self.me["aim"] = gun_aim
        aim,fire,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertEqual(fire,[True,True])
        self.assertEqual(aim,gun_aim)

    def test_full_charge_acquires_beam_aim_before_releasing(self):
        self.laser["charge"] = self.laser["stats"]["charge"]
        self.me["aim"] = self.combat.solve(self.me,self.target,self.gun)[0]
        beam_aim = self.combat.solve(self.me,self.target,self.laser)[0]
        aim,fire,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertEqual(aim,beam_aim)
        self.assertTrue(fire[1])
        self.assertFalse(fire[0])
        self.me["aim"] = beam_aim
        _,fire,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertFalse(fire[1])

    def test_empty_or_reloading_gun_does_not_steal_charge_aim(self):
        self.laser["charge"] = .3
        beam_aim = self.combat.solve(self.me,self.target,self.laser)[0]
        self.gun["ammo"] = 0
        aim,_,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertEqual(aim,beam_aim)
        self.gun.update(ammo=6,reload=1)
        aim,_,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertEqual(aim,beam_aim)

    def test_stationary_target_can_fire_gun_while_releasing_laser(self):
        self.target["vel"] = [0,0,0]
        self.laser["charge"] = self.laser["stats"]["charge"]
        self.me["aim"] = self.combat.solve(self.me,self.target,self.laser)[0]
        _,fire,_ = self.combat.action(self.me,[self.target],False,False)
        self.assertEqual(fire,[True,False])

    def test_feedback_model_keeps_gun_active_and_full_laser_releases(self):
        result = simulate(self.combat,self.h["config"],self.me)
        self.assertGreaterEqual(result["gun_shots_during_charge"],20)
        self.assertGreaterEqual(result["gun_hits"],60)
        self.assertGreaterEqual(result["laser_hits"],12)
        self.assertEqual(result["full_charge_shots"],result["laser_shots"])
        self.assertEqual(result["forced_laser_shots"],0)


if __name__ == "__main__":
    unittest.main()
