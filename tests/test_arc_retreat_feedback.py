"""Full-Bot feedback against a legal moving gun/arc pursuer on the public map.

The baseline differs only by a pass-through movement hook. Both choose goals,
weapons, recovery and targets at10Hz; physical acceleration, shots and damage
resolve at20Hz. Both unknown turn/fire orders are tested, not asserted as engine
truth. These are controlled scenarios, not practice-score predictions.
"""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

from test_bot import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"tools"))
sys.path.insert(0, str(ROOT/"tests"))
from arc_trade import ArcPhysicsBase
from test_bot import fixture
from arc_physics import move
from ground_lab import lead, slew
from sentinel.geometry import distance, unit
from sentinel.strategy import Bot


class NoSpacing:
    def choose(self, obs, move, boost, **kwargs):
        return move, boost


class SpacingSpy:
    def __init__(self, underlying):
        self.underlying = underlying
        self.overrides = 0
        self.records = []

    def choose(self, obs, move, boost, **kwargs):
        result = self.underlying.choose(obs, move, boost, **kwargs)
        self.overrides += result[0] != move
        enemy = obs["mechs"][0]
        me = obs["self"]
        gap = distance(me["pos"], enemy["pos"])
        norm = max(1e-9, math.hypot(*move))
        away = [(me["pos"][i]-enemy["pos"][i])/max(1, gap) for i in range(2)]
        self.records.append(dict(t=obs["t"]-100, move=move, ordinary_boost=boost,
            gap=gap, away_dot=sum(move[i]/norm*away[i] for i in range(2)),
            closing=sum(enemy["vel"][i]*away[i] for i in range(2)),
            facing=abs((math.atan2(-away[1],-away[0])-me["aim"][0]+math.pi)%math.tau-math.pi),
            reason=self.underlying.reason))
        return result

    @property
    def reason(self):
        return self.underlying.reason


class BotTrade(ArcPhysicsBase):
    def __init__(self, enabled, *args, **kwargs):
        super().__init__(enabled, *args, **kwargs)
        self.hello, self.initial = fixture()
        self.bot = Bot(self.hello)
        if not enabled:
            self.bot.arc_retreat = NoSpacing()
        else:
            self.bot.arc_retreat = SpacingSpy(self.bot.arc_retreat)
        self.zone = copy.deepcopy(self.initial["zone"])
        self.zone.update(center=[0, 0], radius=470, next_center=[0, 0], next_radius=470,
                         shrink_start=500, shrink_end=550)
        self.boost_added = 0
        self.jumps = 0

    def observation(self, tick):
        obs = copy.deepcopy(self.initial)
        me = {key: copy.deepcopy(value) for key, value in self.me.items() if not key.startswith("_")}
        for weapon in me["weapons"]:
            for key in list(weapon):
                if key.startswith("_"):
                    weapon.pop(key)
            weapon["cooldown"] = max(0, weapon.get("cooldown", 0))
        enemy = self.view(self.enemy)
        enemy.update(weapons=["gun", "lightning"], charging=False)
        obs.update(t=100+self.now, tick=tick, alive=16, self=me, mechs=[enemy],
            crates=[], cubes=[], pickups=[], drops=[], offer=None, sounds=[], beams=[],
            events=self.events, zone=self.zone, projectiles=[dict(id=i, kind="gun", pos=bullet["pos"],
            vel=bullet["vel"]) for i, bullet in enumerate(self.bullets) if bullet["by"] == 1])
        self.events = []
        return obs

    def run(self):
        own = {}
        for tick in range(round(self.seconds/.05)):
            self.now = tick*.05
            if tick % 2 == 0:
                own = self.bot.act(self.observation(tick))
                self.boost_added = getattr(self.bot.arc_retreat, "overrides", 0)
                self.jumps += bool(own.get("jump"))
                self.trace.append(dict(t=self.now, gap=distance(self.me["pos"], self.enemy["pos"]),
                    hp=self.me["hp"], enemy_hp=self.enemy["hp"], boost=own["boost"], mode=self.bot.mode,
                    charge=self.me["weapons"][1]["charge"],
                    reason=getattr(self.bot.arc_retreat, "reason", "disabled")))
            origin = [*self.enemy["pos"][:2], self.enemy["pos"][2]+7]
            point = [*self.me["pos"][:2], self.me["pos"][2]+4.5]
            enemy_aim = lead(origin, point, self.me["vel"], 252)
            gap = distance(self.me["pos"], self.enemy["pos"])
            direction = unit(self.me["pos"][0]-self.enemy["pos"][0], self.me["pos"][1]-self.enemy["pos"][1])
            enemy_action = dict(move=list(direction), boost=False, aim=enemy_aim,
                fire=[self.world.line_clear(origin, point) and gap <= 230,
                      gap <= 45 and self.world.line_clear(origin, point)],
                reload=self.enemy["weapons"][0]["ammo"] == 0)
            actions = [own, enemy_action]
            positions = [list(actor["pos"]) for actor in self.entities]
            for actor, action in zip(self.entities, actions):
                laser = actor["weapons"][1]
                charging = laser["kind"] == "laser" and (laser["charge"] > 0 or
                    (action["fire"][1] and laser["cooldown"] <= 0))
                self.collisions += not move(actor, action, self.world, charging)
            self.projectiles(positions)
            if self.me["hp"] <= 0 or self.enemy["hp"] <= 0:
                break
            for actor, action in zip(self.entities, actions):
                if not self.before_turn:
                    actor["aim"] = [slew(actor["aim"][0], action["aim"][0], .2, True),
                                    slew(actor["aim"][1], action["aim"][1], .15)]
                self.shot(actor, action)
                if self.before_turn:
                    actor["aim"] = [slew(actor["aim"][0], action["aim"][0], .2, True),
                                    slew(actor["aim"][1], action["aim"][1], .15)]
            self.boost_seconds += .05*own["boost"]
            self.arc_seconds += .05*(distance(self.me["pos"], self.enemy["pos"]) <= 45)
            self.min_energy = min(self.min_energy, self.me["energy"])
            if self.me["hp"] <= 0 or self.enemy["hp"] <= 0 or self.collisions or self.jumps:
                break
        return dict(enabled=self.enabled, before_turn=self.before_turn, seconds=self.now+.05,
            player_hp=self.me["hp"], enemy_hp=self.enemy["hp"], gap=distance(self.me["pos"], self.enemy["pos"]),
            damage=self.damage, hits=self.hits, shots=self.shots, charge_interrupts=self.short_count,
            boost_seconds=self.boost_seconds, arc_range_seconds=self.arc_seconds,
            min_energy=self.min_energy, collision_ticks=self.collisions, ignored_jumps=self.jumps,
            added_decisions=self.boost_added, trace=self.trace,
            hook_records=getattr(self.bot.arc_retreat, "records", []))


class ArcRetreatFeedbackTests(unittest.TestCase):
    def test_coherent_retreat_reduces_real_arcs_in_full_bot_under_both_update_orders(self):
        for order in (False, True):
            for seed in (11, 47, 83):
                with self.subTest(before_turn=order, seed=seed):
                    baseline = BotTrade(False, gap=55, seed=seed, before_turn=order).run()
                    candidate = BotTrade(True, gap=55, seed=seed, before_turn=order).run()
                    self.assertGreater(candidate["player_hp"], baseline["player_hp"])
                    self.assertGreaterEqual(candidate["player_hp"], 400)
                    self.assertLessEqual(candidate["enemy_hp"], 0)
                    self.assertLess(candidate["hits"][1]["lightning"], baseline["hits"][1]["lightning"])
                    self.assertGreaterEqual(candidate["hits"][0]["laser"], baseline["hits"][0]["laser"])
                    self.assertLessEqual(candidate["boost_seconds"], baseline["boost_seconds"])
                    self.assertEqual(candidate["collision_ticks"], 0)
                    self.assertEqual(candidate["ignored_jumps"], 0)

    def test_initially_too_close_and_initially_far_controls_keep_their_outcomes(self):
        for gap in (48, 70):
            for order in (False, True):
                with self.subTest(gap=gap, before_turn=order):
                    baseline = BotTrade(False, gap=gap, seed=47, before_turn=order).run()
                    candidate = BotTrade(True, gap=gap, seed=47, before_turn=order).run()
                    if gap == 48:
                        # Original A* also has a wall-clock work cap, so two
                        # independent runs may differ by a final damage tick.
                        # The new controller must be strictly inert and retain
                        # the same death outcome in this too-close control.
                        self.assertEqual(candidate["added_decisions"], 0)
                        self.assertLessEqual(candidate["player_hp"], 0)
                        self.assertLessEqual(baseline["player_hp"], 0)
                    else:
                        self.assertEqual(candidate["player_hp"], baseline["player_hp"])
                        self.assertEqual(candidate["enemy_hp"], baseline["enemy_hp"])
                        self.assertEqual(candidate["hits"][1]["lightning"], baseline["hits"][1]["lightning"])
                    self.assertEqual(candidate["collision_ticks"], 0)


if __name__ == "__main__" and "--measure" not in sys.argv:
    unittest.main()
elif __name__ == "__main__":
    rows = []
    for gap in (48, 55, 70):
        for order in (False, True):
            baseline = BotTrade(False, gap=gap, seed=47, before_turn=order).run()
            candidate = BotTrade(True, gap=gap, seed=47, before_turn=order).run()
            rows.append(dict(gap=gap, before_turn=order, baseline=baseline, candidate=candidate))
            print(json.dumps(dict(gap=gap, before_turn=order,
                base_hp=baseline["player_hp"], stride_hp=candidate["player_hp"],
                base_enemy=baseline["enemy_hp"], stride_enemy=candidate["enemy_hp"],
                base_arcs=baseline["hits"][1]["lightning"], stride_arcs=candidate["hits"][1]["lightning"],
                additional_decisions=candidate["added_decisions"],
                collisions=candidate["collision_ticks"], jumps=candidate["ignored_jumps"])))
    (Path(__file__).parent/"arc_retreat_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
