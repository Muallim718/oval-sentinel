"""Reactive two-gunner target sequencing, not a placement predictor.

Declared starting snapshot: gun+arc player, one healthy nearby gunner and one
already-wounded90HP gunner. Both gun hunters move/aim/fire from the first tick.
No damage event or successful hit is fabricated to enable the target selector.
"""
import copy
import json
import math
from pathlib import Path
import sys
import time
import unittest

PROJECT=Path(__file__).resolve().parents[1]
if len(sys.argv)>2 and sys.argv[1]=="--simulate":
    PROJECT=Path(sys.argv[2]).resolve()
sys.path[:0]=[str(PROJECT),str(PROJECT/"tests"),str(PROJECT/"tools")]
from test_reload_arm_feedback import ArmFeedback
from ground_lab import DT, lead
from sentinel.navigation import Navigator


class FinishFeedback(ArmFeedback):
    def __init__(self, root=PROJECT, seed=47, *, armor=0, ammo=12, weak_hp=90, seconds=6,
                 strong_behind=False):
        super().__init__(root,seed,"lightning",seconds)
        self.me=self.entity(0,[0,0,0],1400)
        self.strong=self.entity(1,[-25,0,0] if strong_behind else [30,-10,0],1400)
        self.weak=self.entity(2,[100,40,0],weak_hp)
        self.weak["stats"]["armor"]=armor
        self.weak["upgrades"]=["armor"]*round(armor/.08)
        self.enemy=self.strong
        self.enemies=[self.strong,self.weak]
        self.entities=[self.me,*self.enemies]
        self.me["weapons"][1]=dict(kind="lightning",cooldown=0,
            stats=copy.deepcopy(self.config["weapons"]["lightning"]))
        self.me["weapons"][0]["ammo"]=ammo
        for actor in self.entities:
            actor["_combat"],actor["_spent"]=29.5,29.5
            actor["weapons"][0].update(reload=0,cooldown=0)
            other=self.weak if actor["id"]==0 else self.me
            actor["aim"]=lead([*actor["pos"][:2],actor["pos"][2]+actor["stats"]["muzzle_height"]],
                [*other["pos"][:2],other["pos"][2]+other["stats"]["height"]*.5],[0,0,0],252)
        self.enemy_nav={e["id"]:Navigator(self.world,self.config["mech"])for e in self.enemies}
        self.enemy_waypoints={}
        self.pickups=[]
        self.deaths={}
        self.jump_requests=0
        self.body_collision=False
        self.damage_log=[]
        self.max_decision_ms=0
        self.selections=[]
        self.gun_shots={actor["id"]:0 for actor in self.entities}
        self.t=30

    def weapon(self, actor, action):
        # Shared documented automatic reload; no partial-magazine refill.
        gun=actor["weapons"][0]
        if gun["ammo"]<=0 and gun["reload"]<=0:
            action={**action,"reload":True}
        first=self.next_bullet
        super().weapon(actor,action)
        self.gun_shots[actor["id"]]+=self.next_bullet-first
        if gun["ammo"]<=0 and gun["reload"]<=0:
            gun["reload"]=gun["stats"]["reload"]
        # The barrel is forward of the center, matching the public hit rule.
        for bullet in self.bullets:
            if bullet["id"]<first:
                continue
            origin=list(bullet["pos"])
            speed=math.sqrt(sum(v*v for v in bullet["vel"]))
            barrel=[origin[i]+bullet["vel"][i]/speed*(actor["stats"]["radius"]+.5)for i in range(3)]
            if not self.world.line_clear(origin,barrel):
                bullet["remaining"]=0
            bullet["pos"]=barrel

    def projectiles(self):
        self.bullets=[b for b in self.bullets if b["remaining"]>0]
        count=len(self.events)
        super().projectiles()
        for event in self.events[count:]:
            if event["type"] in ("damaged","hit"):
                self.damage_log.append(dict(t=round(self.t-30,3),**event))
        for enemy in self.enemies:
            if enemy["hp"]<=0 and enemy["id"] not in self.deaths:
                self.deaths[enemy["id"]]=dict(t=round(self.t-30,3),player_hp=self.me["hp"])

    def run(self):
        action={}
        for tick in range(round(self.seconds/DT)):
            self.t=30+tick*DT
            if tick%2==0:
                obs=self.observation(tick)
                started=time.perf_counter();action=self.bot.act(obs)
                self.max_decision_ms=max(self.max_decision_ms,(time.perf_counter()-started)*1000)
                self.jump_requests+=bool(action.get("jump"))
                choice=getattr(getattr(self.bot,"finish_target",None),"choice",None)
                self.selections.append(dict(t=round(self.t-30,3),mode=self.bot.mode,
                    target=self.bot.combat.locked_id,finish=choice.target["id"]if choice else None,
                    aim=list(action["aim"]),fire=list(action["fire"]),hp=self.me["hp"],
                    weak_hp=self.weak["hp"],strong_hp=self.strong["hp"]))
            controls={0:action}
            controls.update({e["id"]:self.enemy_action(e,tick)for e in self.enemies if e["hp"]>0})
            for actor in self.entities:
                if actor["hp"]<=0:
                    continue
                self.move_entity(actor,controls[actor["id"]])
                self.weapon(actor,controls[actor["id"]])
                self.body_collision|=not self.world.body_clear(*actor["pos"],actor["stats"]["radius"]-.001,
                    actor["stats"]["height"],actor["stats"]["step_up"])
            self.projectiles()
            if self.me["hp"]<=0 or self.jump_requests or self.body_collision:
                break
        return dict(seed=self.hello["seed"],hp=max(0,self.me["hp"]),weak_hp=max(0,self.weak["hp"]),
            strong_hp=max(0,self.strong["hp"]),deaths=self.deaths,damage_taken=self.metrics["damage_taken"],
            damage_dealt=self.metrics["damage_dealt"],healing=self.metrics["healing"],
            shots=self.metrics["shots"],arc_hits=self.secondary_hits,energy=self.me["energy"],
            gun_shots=self.gun_shots,
            jumps=self.jump_requests,body_collision=self.body_collision,max_decision_ms=self.max_decision_ms,
            selections=self.selections,damage_log=self.damage_log)


class FinishFeedbackTests(unittest.TestCase):
    def test_actual_two_active_gunners_and_arc_remove_the_weak_lane(self):
        for seed in (47,71):
            result=FinishFeedback(seed=seed).run()
            self.assertEqual(result["selections"][0]["target"],2)
            self.assertEqual(result["selections"][0]["fire"],[True,False])
            self.assertLess(result["deaths"][2]["t"],1.25)
            self.assertTrue(any(e["type"]=="damaged" and e["by"]==1 for e in result["damage_log"]))
            self.assertGreater(result["gun_shots"][2],0)  # A real active shooter may miss.
            self.assertEqual(result["healing"],0)
            self.assertEqual(result["jumps"],0)
            self.assertFalse(result["body_collision"])

    def test_maximum_public_armor_requires_actual_three_round_hits(self):
        result=FinishFeedback(armor=.24).run()
        weak_hits=[e for e in result["damage_log"]if e["type"]=="hit"and e["target"]==2]
        self.assertGreaterEqual(len(weak_hits),3)
        self.assertGreaterEqual(sum(e["amount"]for e in weak_hits),90)
        self.assertLess(result["deaths"][2]["t"],1.25)

    def test_ammo_and_health_negative_controls_retain_the_original_first_target(self):
        for kwargs in (dict(ammo=2),dict(weak_hp=110)):
            result=FinishFeedback(seconds=.1,**kwargs).run()
            self.assertIsNone(result["selections"][0]["finish"])
            self.assertEqual(result["selections"][0]["target"],1)

    def test_real_new_rear_hit_cancels_the_optional_target_lease(self):
        result=FinishFeedback(strong_behind=True,seconds=.7).run()
        rear=[e for e in result["damage_log"]if e["type"]=="damaged" and e["by"]==1 and e.get("rear")]
        self.assertTrue(rear)
        after=[frame for frame in result["selections"]if frame["t"]>rear[0]["t"]]
        self.assertTrue(after)
        self.assertIsNone(after[0]["finish"])


if __name__=="__main__":
    if len(sys.argv)>2 and sys.argv[1]=="--simulate":
        results=[]
        for armor in (0,.24):
            for seed in (47,71):
                result=FinishFeedback(PROJECT,seed,armor=armor).run()
                result["armor"]=armor
                results.append(result)
        if len(sys.argv)>3:
            Path(sys.argv[3]).write_text(json.dumps(dict(project=str(PROJECT),results=results),indent=2)+"\n")
        for result in results:
            print(json.dumps({k:v for k,v in result.items()if k not in("selections","damage_log")}))
    else:
        unittest.main()
