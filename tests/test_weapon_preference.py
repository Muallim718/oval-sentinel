"""Lightning preference only: weapon goals and safe replacement, not combat AI."""
import copy
import unittest
from test_bot import fixture, flat_world
from sentinel.combat import Combat
from sentinel.navigation import Navigator
from sentinel.strategy import Bot


class WeaponPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.h,self.o = fixture()
        self.bot = Bot(self.h)
        self.bot.world = flat_world()
        self.bot.nav = Navigator(self.bot.world,self.h["config"]["mech"])
        self.bot.combat = Combat(self.bot.world,self.h["config"])
        self.me = self.o["self"]
        self.me.update(pos=[-70,0,0],vel=[0,0,0],aim=[0,0])
        self.o["zone"].update(center=[0,0],radius=118,next_center=[0,0],next_radius=118,
                              shrink_start=500,shrink_end=550)

    def weapon(self,kind,charge=0):
        return {"kind":kind,"cooldown":0,"charge":charge,
                "stats":copy.deepcopy(self.h["config"]["weapons"][kind])}

    def pickup(self,kind,where=None,item_id=8001):
        return {"id":item_id,"kind":kind,"pos":where or [-70,0,0]}

    def test_equally_distant_lightning_is_preferred_to_laser(self):
        self.o["pickups"] = [self.pickup("laser",[-50,10,0]),
                              self.pickup("lightning",[-50,-10,0],8002)]
        self.bot.act(self.o)
        self.assertEqual(self.bot.goal_kind,"weapon")
        self.assertEqual(self.bot.goal,(-50,-10))

    def test_empty_slot_takes_lightning_first_but_keeps_gun(self):
        self.o["pickups"] = [self.pickup("laser"),self.pickup("lightning",item_id=8002)]
        action = self.bot.act(self.o)
        self.assertEqual(action["take"],8002)
        self.assertNotIn("drop",action)

    def test_nearby_lightning_replaces_an_idle_laser(self):
        self.me["weapons"][1] = self.weapon("laser")
        self.o["pickups"] = [self.pickup("lightning")]
        action = self.bot.act(self.o)
        self.assertEqual(action["take"],8001)
        self.assertEqual(action["drop"],1)

    def test_does_not_swap_a_charging_laser(self):
        self.me["weapons"][1] = self.weapon("laser",charge=.4)
        self.o["pickups"] = [self.pickup("lightning")]
        action = self.bot.act(self.o)
        self.assertNotIn("take",action)
        self.assertNotIn("drop",action)

    def test_swap_does_not_simultaneously_start_a_laser_charge(self):
        self.me["weapons"][1] = self.weapon("laser")
        self.o["mechs"] = [{"id":1,"kind":"mech","pos":[-10,0,0],"vel":[0,0,0],
                            "hp":1400,"max_hp":1400,"weapons":["gun"]}]
        self.o["pickups"] = [self.pickup("lightning")]
        action = self.bot.act(self.o)
        self.assertEqual(action["drop"],1)
        self.assertFalse(action["fire"][1])

    def test_lightning_is_not_replaced_by_laser_or_mortar(self):
        self.me["weapons"][1] = self.weapon("lightning")
        self.o["pickups"] = [self.pickup("laser"),self.pickup("mortar",item_id=8002)]
        action = self.bot.act(self.o)
        self.assertNotIn("take",action)
        self.assertNotIn("drop",action)

    def test_laser_is_still_taken_when_it_is_the_only_weapon(self):
        self.o["pickups"] = [self.pickup("laser")]
        self.assertEqual(self.bot.act(self.o)["take"],8001)

    def test_replacement_still_respects_vertical_pickup_limit(self):
        self.me["weapons"][1] = self.weapon("laser")
        self.o["pickups"] = [self.pickup("lightning",[-70,0,20])]
        self.assertNotIn("take",self.bot.act(self.o))

    def test_idle_laser_can_plan_a_lightning_upgrade(self):
        self.me["weapons"][1] = self.weapon("laser")
        self.o["pickups"] = [self.pickup("lightning",[-15,0,0])]
        self.bot.act(self.o)
        self.assertEqual(self.bot.goal_kind,"weapon")
        self.assertEqual(self.bot.goal,(-15,0))


if __name__ == "__main__":
    unittest.main()
