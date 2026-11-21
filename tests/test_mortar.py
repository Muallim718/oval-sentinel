"""A real withheld mortar hit and a bounded handoff of the shared torso."""
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.combat import Combat
from sentinel.geometry import angle_error
from sentinel.mortar import Decision, MortarFallback


class Adapter:
    """Compare the same runtime with or without its new fallback."""
    def __init__(self, world, config, enabled):
        self.combat = Combat(world, config)
        self.handoffs = 0
        assess = self.combat.mortar_fallback.assess

        def record(*args, **kwargs):
            decision = assess(*args, **kwargs) if enabled else Decision(False, False, "baseline")
            self.handoffs += decision.handoff_gun
            return decision

        self.combat.mortar_fallback.assess = record

    def action(self, me, target):
        return self.combat.action(me, [target], False, False)[:2]


def feedback(enabled, radius=45, speed=19.5, world=None, before_turn=False, seconds=2):
    hello, obs = fixture()
    config = hello["config"]
    world = world or flat_world()
    me = copy.deepcopy(obs["self"])
    me.update(pos=[0, 0, 0], vel=[0, 0, 0], aim=[0, 0], cubes=0, grounded=True)
    me["weapons"] = [{"kind": "gun", "stats": config["weapons"]["gun"], "ammo": 12, "reload": 0, "cooldown": 0},
                     {"kind": "mortar", "stats": config["weapons"]["mortar"], "cooldown": 0}]
    controller = Adapter(world, config, enabled)
    held, command = [False, False], [0, 0]
    projectiles, shots, hits = [], [0, 0], [0, 0]

    def target(now):
        theta = speed/radius*now
        return {"id": 5, "kind": "mech", "pos": [radius*math.cos(theta), radius*math.sin(theta), 0],
                "vel": [-speed*math.sin(theta), speed*math.cos(theta), 0], "cubes": 0,
                "hp": 1400, "max_hp": 1400, "weapons": ["gun", "lightning"]}

    def turn():
        me["aim"][0] += max(-.2, min(.2, angle_error(command[0], me["aim"][0])))
        me["aim"][1] += max(-.15, min(.15, command[1]-me["aim"][1]))

    for tick in range(round(seconds/.05)):
        now = tick*.05
        for weapon in me["weapons"]:
            weapon["cooldown"] = max(0, weapon["cooldown"]-.05)
        if tick%2 == 0:
            command, held = controller.action(me, target(now))
        if not before_turn:
            turn()
        for slot, weapon in enumerate(me["weapons"]):
            if not held[slot] or weapon["cooldown"] > 1e-9 or (slot == 0 and weapon["ammo"] <= 0):
                continue
            yaw, pitch = me["aim"]
            direction = [math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)]
            muzzle = [0, 0, 7 if slot == 0 else 9.5]
            origin = [muzzle[i]+direction[i]*3 for i in range(3)]
            if world.line_clear(muzzle, origin):
                projectiles.append((slot, now+.05, origin, [weapon["stats"]["speed"]*d for d in direction]))
            shots[slot] += 1
            weapon["cooldown"] = weapon["stats"]["cooldown"]
            if slot == 0:
                weapon["ammo"] -= 1
        if before_turn:
            turn()
        flying = []
        for slot, emitted, origin, velocity in projectiles:
            if emitted >= now+.05-1e-9:
                flying.append((slot, emitted, origin, velocity))
                continue
            found = False
            previous = [origin[i]+velocity[i]*(now-emitted) for i in range(3)]
            previous[2] -= (11*(now-emitted)**2 if slot else 0)
            for sub in range(1, 11):
                flight = now+.005*sub-emitted
                point = [origin[0]+velocity[0]*flight, origin[1]+velocity[1]*flight,
                         origin[2]+velocity[2]*flight-(11*flight*flight if slot else 0)]
                body = target(emitted+flight)["pos"]
                if not world.line_clear(previous, point):
                    found = True
                    break
                if math.hypot(point[0]-body[0], point[1]-body[1]) < 2.5 and 0 < point[2] < 9:
                    hits[slot] += 1
                    found = True
                    break
                if point[2] <= world.ground(*point[:2]):
                    found = True
                    break
                previous = point
            if not found:
                flying.append((slot, emitted, origin, velocity))
        projectiles = flying
    return shots, hits, controller.handoffs


class MortarTests(unittest.TestCase):
    def setUp(self):
        self.hello, obs = fixture()
        self.config = self.hello["config"]
        self.me = copy.deepcopy(obs["self"])
        self.me.update(pos=[0, 0, 0], vel=[0, 0, 0], aim=[0, 0], cubes=0, grounded=True)
        self.mortar = {"kind": "mortar", "stats": self.config["weapons"]["mortar"], "cooldown": 0}
        self.me["weapons"][1] = self.mortar
        self.target = {"id": 5, "kind": "mech", "pos": [45, 0, 0], "vel": [0, 19.5, 0], "cubes": 0}
        self.world = flat_world()
        self.fallback = MortarFallback(self.world, self.config)
        self.aim = Combat(self.world, self.config).solve(self.me, self.target, self.mortar)[0]
        self.me["aim"] = [self.aim[0]-.0433333, self.aim[1]]

    def test_two_real_launch_arcs_replace_legacy_tracking_rejection(self):
        self.target.update(pos=[30, 0, 0], vel=[0, 11.7, 0])
        self.aim = Combat(self.world, self.config).solve(self.me, self.target, self.mortar)[0]
        self.me["aim"] = [self.aim[0]-.039, self.aim[1]]
        self.assertGreater(abs(angle_error(self.aim[0], self.me["aim"][0])), .035)
        decision = self.fallback.assess(self.me, self.target, self.mortar, self.aim)
        self.assertTrue(decision.extra_fire)
        self.assertFalse(decision.handoff_gun)

    def test_20hz_moving_target_gets_real_mortar_and_gun_damage(self):
        for order in (False, True):
            old_shots, old_hits, _ = feedback(False, before_turn=order)
            shots, hits, _ = feedback(True, before_turn=order)
            self.assertEqual(old_shots, [0, 0])
            self.assertEqual(old_hits, [0, 0])
            self.assertEqual(shots[1], 0)  # old aim is unsafe after the 50ms move
            self.assertEqual(hits[1], 0)
            self.assertGreater(shots[0], 0)
            self.assertGreater(hits[0], 0)

    def test_ordinary_walk_speed_at_30m_also_unlocks_a_real_shell(self):
        old_shots, _, _ = feedback(False, radius=30, speed=11.7)
        shots, hits, _ = feedback(True, radius=30, speed=11.7)
        self.assertEqual(old_shots[1], 0)
        self.assertGreaterEqual(shots[1], 1)
        self.assertGreaterEqual(hits[1], 1)

    def test_actual_overhang_collision_yields_enough_gun_time_to_hit(self):
        # The old sampled center launch clears under this lip, but the actual
        # 3m forward barrel advances before gravity and hits its underside.
        world = flat_world([rectangle(4, -20, 5, 20, base=9.45, top=20)])
        self.assertTrue(world.body_clear(0, 0, 0, 2.5, 9))
        self.assertIsNotNone(Combat(world, self.config).solve(self.me, self.target, self.mortar))
        # This initial sector is physically blocked. After the target rotates
        # farther around the lip, a newly valid mortar is allowed to reclaim it.
        old_shots, old_hits, _ = feedback(False, world=world, seconds=.6)
        shots, hits, handoffs = feedback(True, world=world, seconds=.6)
        self.assertEqual(old_shots, [0, 0])
        self.assertEqual(old_hits, [0, 0])
        self.assertEqual(shots[1], 0)
        self.assertGreaterEqual(handoffs, 4)
        self.assertGreaterEqual(shots[0], 1)
        self.assertGreaterEqual(hits[0], 1)

    def test_current_or_next_wall_collision_cannot_gain_trigger(self):
        wall = flat_world([rectangle(12, -30, 15, 30)])
        decision = MortarFallback(wall, self.config).assess(self.me, self.target, self.mortar, self.aim)
        self.assertFalse(decision.extra_fire)
        self.me["aim"] = [self.aim[0]-.5, self.aim[1]]
        self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).extra_fire)

    def test_legacy_aligned_and_ordinary_cooldown_preserve_old_controller(self):
        result = self.fallback.assess(self.me, self.target, self.mortar, self.aim, legacy_aligned=True)
        self.assertFalse(result.extra_fire)
        self.assertFalse(result.handoff_gun)
        self.mortar["cooldown"] = .3
        for _ in range(5):
            result = self.fallback.assess(self.me, self.target, self.mortar, self.aim)
            self.assertFalse(result.extra_fire)
            self.assertFalse(result.handoff_gun)

    def test_handoff_is_four_consecutive_decisions_and_rechecks_valid_shot(self):
        self.me["aim"] = [math.pi, 0]
        results = [self.fallback.assess(self.me, self.target, self.mortar, self.aim) for _ in range(7)]
        self.assertEqual([result.handoff_gun for result in results], [False, False, True, True, True, True, False])
        self.fallback.gun_left = 3
        self.me["aim"] = self.aim[:]
        result = self.fallback.assess(self.me, self.target, self.mortar, self.aim)
        self.assertTrue(result.extra_fire)
        self.assertFalse(result.handoff_gun)
        self.assertEqual(self.fallback.gun_left, 0)

    def test_self_splash_airborne_and_expired_budget_fail_closed(self):
        self.target.update(pos=[16.2, 0, 0], vel=[0, 0, 0])
        self.aim = Combat(self.world, self.config).solve(self.me, self.target, self.mortar)[0]
        self.me["aim"] = self.aim[:]
        self.me["vel"] = [19.5, 0, 0]
        self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).extra_fire)
        self.me["vel"] = [0, 0, 0]
        self.me["grounded"] = False
        self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).extra_fire)
        self.me["grounded"] = True
        with patch("sentinel.mortar.time.perf_counter", side_effect=[0, 1]):
            self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).extra_fire)

    def test_no_handoff_without_a_loaded_gun_and_target_change_resets(self):
        self.me["aim"] = [math.pi, 0]
        self.me["weapons"][0]["ammo"] = 0
        for _ in range(5):
            self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).handoff_gun)
        self.me["weapons"][0]["ammo"] = 12
        for _ in range(3):
            result = self.fallback.assess(self.me, self.target, self.mortar, self.aim)
        self.assertTrue(result.handoff_gun)
        self.target["id"] = 6
        self.assertFalse(self.fallback.assess(self.me, self.target, self.mortar, self.aim).handoff_gun)


if __name__ == "__main__":
    unittest.main()
