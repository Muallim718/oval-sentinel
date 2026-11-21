"""Run the actual Bot with and without its screened-finish policy.

No damage event is inserted to enable either policy. HP800 is the initial hurt
state; every later event comes from actual emitted projectile/cylinder contacts.
"""
import json
import math
from pathlib import Path
import sys
import unittest

from test_bot import ROOT
sys.path.insert(0, str(ROOT/"tools"))
from ground_lab import Lab, DT, lead
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner, firing_lane
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from sentinel.opener import Opener
from sentinel.salvage import KillSalvage
from sentinel.selective_cover import SelectiveCover


class SelectiveFeedback(Lab):
    def __init__(self, enabled, weak_reload=False, seed=11, seconds=4):
        super().__init__(ROOT, "crossfire_cover", seed, seconds)
        self.enabled, self.weak_reload = enabled, weak_reload
        self.me = self.entity(0, [-12, -51, 0], 800)
        self.strong = self.entity(1, [70, -20, 0], 1400)
        self.weak = self.entity(2, [-55, -51, 0], 140)
        self.enemies = [self.strong, self.weak]
        self.entities = [self.me, *self.enemies]
        for entity in self.entities:
            entity["_combat"], entity["_spent"] = 29.5, 29.5
        if weak_reload:
            self.weak["weapons"][0].update(ammo=0, reload=2.4)
        for enemy in self.enemies:
            enemy["aim"] = lead([*enemy["pos"][:2], 7], [*self.me["pos"][:2], 4.5], [0, 0, 0], 252)
        self.me["aim"] = lead([*self.me["pos"][:2], 7], [*self.weak["pos"][:2], 4.5], [0, 0, 0], 252)
        self.bot.world, self.bot.nav = self.world, Navigator(self.world, self.config["mech"])
        self.bot.combat, self.bot.cover = Combat(self.world, self.config), CoverPlanner(self.world, self.config)
        self.bot.motion = GroundSteering(self.world, self.config)
        self.bot.opener, self.bot.salvage = Opener(self.world, self.config), KillSalvage(self.world, self.config)
        self.selective = SelectiveCover(self.world, self.config, self.bot.cover)
        self.bot.selective_cover = self.selective
        if not enabled:
            self.selective.choose = lambda *args, **kwargs: None
        self.enemy_nav = {e["id"]: Navigator(self.world, self.config["mech"]) for e in self.enemies}
        self.enemy_waypoints = {}
        self.t, self.weak_kill_at, self.first_fire, self.first_damage = 30., None, None, None
        self.accepted, self.trace = 0, []
        # The85m strong attacker is behind the current weak-facing torso.
        # Earn its official5s tracking with a real earlier eye sightline; do not
        # inject a known enemy or fake damage to make the mode gate change.
        weak_facing = list(self.me["aim"])
        self.me["aim"] = lead([*self.me["pos"][:2], 7], [*self.strong["pos"][:2], 4.5], [0, 0, 0], 252)
        self.t = 29
        prior = self.observation(-20)
        self.prior_observed = [e["id"] for e in prior["mechs"]]
        self.bot.remember(prior)
        self.me["aim"], self.t = weak_facing, 30

    def observation(self, tick):
        obs = super().observation(tick)
        obs["alive"] = 16
        return obs

    def controls(self, obs):
        action = self.bot.act(obs)
        self.accepted += self.selective.plan is not None
        return action

    def run(self):
        action = {}
        for tick in range(round(self.seconds/DT)):
            self.t = 30+tick*DT
            if tick % 2 == 0:
                obs = self.observation(tick)
                if any(e.get("type") == "damaged" for e in obs["events"]) and self.first_damage is None:
                    self.first_damage = self.t-30
                action = self.controls(obs)
                if action["fire"][0] and self.first_fire is None:
                    self.first_fire = self.t-30
                self.trace.append(dict(t=round(self.t-30, 3), pos=list(self.me["pos"]), hp=self.me["hp"],
                    weak_hp=self.weak["hp"], mode=self.bot.mode, fire=action["fire"],
                    selective=self.selective.state, reason=self.selective.reason))
            actions = {0: action}
            actions.update({e["id"]: self.enemy_action(e, tick) for e in self.enemies if e["hp"] > 0})
            for entity in self.entities:
                if entity["hp"] > 0:
                    self.move_entity(entity, actions[entity["id"]])
                    self.weapon(entity, actions[entity["id"]])
            self.projectiles()
            if self.weak["hp"] <= 0 and self.weak_kill_at is None:
                self.weak_kill_at = self.t-30
            if self.me["hp"] <= 0:
                break
        return dict(enabled=self.enabled, weak_reload=self.weak_reload, accepted=self.accepted,
                    weak_kill_at=self.weak_kill_at, first_fire=self.first_fire,
                    first_real_damage_observed=self.first_damage, hp=self.me["hp"],
                    weak_hp=self.weak["hp"], damage_taken=self.metrics["damage_taken"],
                    damage_dealt=self.metrics["damage_dealt"], gun_shots=self.metrics["shots"],
                    healing=self.metrics["healing"], energy=self.me["energy"])


class SelectiveFeedbackTests(unittest.TestCase):
    def test_same_ready_gun_hunters_produce_real_hits_and_a_finish(self):
        baseline = SelectiveFeedback(False).run()
        candidate = SelectiveFeedback(True).run()
        self.assertGreater(candidate["accepted"], 0)
        self.assertIsNotNone(candidate["first_real_damage_observed"])
        self.assertIsNotNone(candidate["weak_kill_at"])
        self.assertGreater(candidate["hp"], 0)
        self.assertLessEqual(candidate["weak_kill_at"], baseline["weak_kill_at"] + 1e-8)
        self.assertEqual(candidate["gun_shots"], baseline["gun_shots"])
        self.assertGreater(candidate["hp"], baseline["hp"])

    def test_real_weak_reload_control_never_fabricates_a_damage_unlock(self):
        model = SelectiveFeedback(True, weak_reload=True)
        candidate = model.run()
        self.assertGreater(candidate["accepted"], 0)
        self.assertIsNotNone(candidate["weak_kill_at"])
        self.assertGreater(candidate["damage_dealt"], 0)
        self.assertIsNone(candidate["first_real_damage_observed"])


if __name__ == "__main__":
    if "--compare" in sys.argv:
        rows = []
        for reload in (False, True):
            for enabled in (False, True):
                rows.append(SelectiveFeedback(enabled, weak_reload=reload).run())
        print(json.dumps(rows, indent=2))
    else:
        unittest.main()
