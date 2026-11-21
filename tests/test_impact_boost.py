"""Real acceleration, gun interception, and bounded sprint follow-through."""
import copy
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.impact_boost import ImpactBoost
from sentinel.movement import GroundSteering


def setup():
    hello, obs = fixture()
    world = flat_world()
    me = obs["self"]
    me.update(pos=[0, 0, 0], vel=[11.7, 0, 0], energy=100, hp=1400, max_hp=1400,
              aim=[math.pi/2, 0], grounded=True, in_zone=True, cubes=0)
    me["weapons"][1] = None
    enemy = {"id": 5, "kind": "mech", "pos": [1.5, 100, 0], "vel": [0, 0, 0],
             "hp": 1400, "weapons": ["gun"], "aim": [-math.pi/2, 0], "charging": False}
    obs.update(t=20, tick=400, mechs=[enemy], events=[],
               projectiles=[{"id": 81, "kind": "gun", "pos": [1.5, 68, 7], "vel": [0, -252, 0]}])
    obs["zone"].update(center=[0, 0], radius=100, next_center=[0, 0], next_radius=100)
    return hello, obs, world, enemy


def physical_feedback(enabled):
    hello, obs, world, enemy = setup()
    config, me = hello["config"], obs["self"]
    steering = GroundSteering(world, config)
    controller = ImpactBoost(world, config)
    command, boosting = [1, 0], False
    bullet = copy.deepcopy(obs["projectiles"][0])
    trace = []
    hit_at = None
    for tick in range(14):
        now = tick*.05
        if tick%2 == 0:
            obs.update(t=20+now, tick=400+tick, projectiles=[bullet] if bullet else [])
            command, boosting = steering.choose(obs, (.525, 35, 0), [(enemy, 1)],
                                               "fight", 65, False, circle=([0, 0], 100))
            ordinary = (list(command), boosting)
            if enabled:
                command, boosting = controller.choose(obs, command, boosting, circle=([0, 0], 100),
                                                       fire=[False, False])
            trace.append((now, ordinary, (list(command), boosting)))
        previous = list(me["pos"])
        speed = me["stats"]["boost_speed"] if boosting else me["stats"]["walk_speed"]
        dx, dy = command[0]*speed-me["vel"][0], command[1]*speed-me["vel"][1]
        fraction = min(1, me["stats"]["ground_accel"]*.05/max(1e-9, math.hypot(dx, dy)))
        me["vel"][0] += dx*fraction
        me["vel"][1] += dy*fraction
        me["pos"][0] += me["vel"][0]*.05
        me["pos"][1] += me["vel"][1]*.05
        self_clear = world.walk_clear(previous, me["pos"], me["stats"]["radius"], me["stats"]["height"],
                                      me["stats"]["step_up"], me["stats"]["max_slope_deg"])
        if not self_clear:
            raise AssertionError("actual body collided during feedback")
        if boosting:
            me["energy"] -= me["stats"]["boost_drain"]*.05
        if bullet:
            before = bullet["pos"][:]
            after = [before[i]+bullet["vel"][i]*.05 for i in range(3)]
            rx, ry = before[0]-previous[0], before[1]-previous[1]
            vx = after[0]-before[0]-(me["pos"][0]-previous[0])
            vy = after[1]-before[1]-(me["pos"][1]-previous[1])
            a, b, c = vx*vx+vy*vy, 2*(rx*vx+ry*vy), rx*rx+ry*ry-me["stats"]["radius"]**2
            discriminant = b*b-4*a*c
            if discriminant >= 0:
                fraction = (-b-math.sqrt(discriminant))/(2*a)
                if 0 <= fraction <= 1:
                    point = [before[i]+(after[i]-before[i])*fraction for i in range(3)]
                    if 0 <= point[2] <= me["stats"]["height"] and world.line_clear(before, point):
                        me["hp"] -= 45
                        hit_at = now+.05*fraction
                        bullet = None
            if bullet:
                bullet["pos"] = after
    return me, hit_at, trace


class ImpactBoostTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs, self.world, self.enemy = setup()
        self.me, self.config = self.obs["self"], self.hello["config"]
        self.controller = ImpactBoost(self.world, self.config)
        self.circle = ([0, 0], 100)

    def choose(self, move=(1, 0), boost=False, **kwargs):
        return self.controller.choose(self.obs, list(move), boost, circle=self.circle, **kwargs)

    def test_real_ordinary_walk_is_hit_but_short_boost_physically_clears(self):
        baseline, baseline_hit, old_trace = physical_feedback(False)
        candidate, candidate_hit, trace = physical_feedback(True)
        self.assertIsNotNone(baseline_hit)
        self.assertLess(baseline_hit, .3)
        self.assertEqual(baseline["hp"], 1355)
        self.assertIsNone(candidate_hit)
        self.assertEqual(candidate["hp"], 1400)
        self.assertEqual(trace[0][1], old_trace[0][1])
        self.assertFalse(trace[0][1][1])
        self.assertTrue(trace[0][2][1])
        self.assertAlmostEqual(candidate["energy"], 93.2)
        self.assertGreaterEqual(candidate["energy"], 26)
        self.assertTrue(all(row[2][1] for row in trace if row[0] < .35))
        self.assertTrue(all(not row[2][1] for row in trace if row[0] >= .4))

    def test_imminent_contact_activates_without_mutating_aim_fire_or_observation(self):
        before = copy.deepcopy(self.obs)
        fire = [True, False]
        move, boost = self.choose(fire=fire)
        self.assertTrue(boost)
        self.assertEqual(move, [1, 0])
        self.assertEqual(fire, [True, False])
        self.assertEqual(self.obs, before)
        self.assertAlmostEqual(self.controller.active_until, 20.35)

    def test_safe_walk_distant_or_occluded_bullet_does_not_spend_energy(self):
        for position in ([5.9, 68, 7], [6.5, 68, 7], [1.5, 300, 7], [1.5, -30, 7]):
            self.obs["projectiles"][0]["pos"] = position
            self.assertEqual(self.choose(), ([1, 0], False))
        self.obs["projectiles"][0]["pos"] = [1.5, 68, 7]
        blocked = ImpactBoost(flat_world([rectangle(-5, 10, 5, 12)]), self.config)
        self.assertEqual(blocked.choose(self.obs, [1, 0], False, circle=self.circle), ([1, 0], False))

    def test_existing_sprint_already_clears_and_is_not_replaced(self):
        self.assertEqual(self.choose(boost=True), ([1, 0], True))
        self.assertLess(self.controller.active_until, self.obs["t"])

    def test_fixed_follow_through_then_exact_expiry_returns_to_ordinary_move(self):
        self.assertTrue(self.choose()[1])
        held = self.controller.command[:]
        self.obs.update(t=20.1, tick=402, projectiles=[])
        self.assertEqual(self.choose(move=(-1, 0)), (held, True))
        self.obs.update(t=20.35, tick=407)
        self.assertEqual(self.choose(move=(-1, 0)), ([-1, 0], False))

    def test_shelter_storm_or_airborne_owns_control_even_during_a_dodge(self):
        for field in ("sheltered", "in_zone", "grounded"):
            hello, obs, world, _ = setup()
            controller = ImpactBoost(world, hello["config"])
            self.assertTrue(controller.choose(obs, [1, 0], False, circle=self.circle)[1])
            obs.update(t=20.1, tick=402)
            kwargs = {}
            if field == "sheltered":
                kwargs[field] = True
            else:
                obs["self"][field] = False
            self.assertEqual(controller.choose(obs, [-1, 0], False, circle=self.circle, **kwargs), ([-1, 0], False))
            self.assertLess(controller.active_until, obs["t"])

    def test_live_body_growth_invalidates_the_stored_boost_path(self):
        world = flat_world([rectangle(15, -20, 16, 20)])
        controller = ImpactBoost(world, self.config)
        self.assertTrue(controller.choose(self.obs, [1, 0], False, circle=self.circle)[1])
        self.obs.update(t=20.1, tick=402, projectiles=[])
        self.me.update(pos=[1.60875, 0, 0], vel=[17.55, 0, 0])
        self.me["stats"]["radius"] = 5
        self.me["stats"]["height"] = 18
        self.assertEqual(controller.choose(self.obs, [1, 0], False, circle=self.circle), ([1, 0], False))

    def test_energy_reserve_crowded_or_mixed_projectiles_fail_closed(self):
        self.me["energy"] = 32
        self.assertEqual(self.choose(), ([1, 0], False))
        self.me["energy"] = 100
        original = self.obs["projectiles"][0]
        self.obs["projectiles"] = [dict(original, id=i) for i in range(7)]
        self.assertEqual(self.choose(), ([1, 0], False))
        self.obs["projectiles"] = [original, {"id": 100, "kind": "mortar", "pos": [40, 0, 15], "vel": [-72, 0, 0]}]
        self.assertEqual(self.choose(), ([1, 0], False))

    def test_zone_and_map_collision_can_veto_all_boost_escape_paths(self):
        self.circle = ([0, 0], 7)
        self.assertEqual(self.choose(), ([1, 0], False))
        corridor = flat_world([rectangle(3.5, -20, 4.5, 20), rectangle(-4.5, -20, -3.5, 20)])
        controller = ImpactBoost(corridor, self.config)
        self.assertEqual(controller.choose(self.obs, [0, 1], False, circle=([0, 0], 100)), ([0, 1], False))

    def test_laser_start_is_not_mistaken_for_full_speed_and_capped_hold_is_unknown(self):
        laser = {"kind": "laser", "stats": self.config["weapons"]["laser"], "charge": 0, "cooldown": 0}
        self.me["weapons"][1] = laser
        self.assertEqual(self.choose(), ([1, 0], False))  # no planned fire supplied
        self.assertEqual(self.choose(fire=[False, True]), ([1, 0], False))
        laser["charge"] = .75
        self.assertEqual(self.choose(fire=[False, True]), ([1, 0], False))

    def test_partial_laser_charge_uses_real_half_speed_boost(self):
        self.me["weapons"][1] = {"kind": "laser", "stats": self.config["weapons"]["laser"], "charge": .4, "cooldown": 0}
        self.me["vel"] = [5.85, 0, 0]
        self.obs["projectiles"][0]["pos"] = [.5, 110, 7]
        self.assertTrue(self.choose(fire=[False, True])[1])

    def test_observed_partial_charge_keeps_followthrough_when_report_caps(self):
        laser = {"kind": "laser", "stats": self.config["weapons"]["laser"], "charge": .55, "cooldown": 0}
        self.me["weapons"][1] = laser
        self.me["vel"] = [5.85, 0, 0]
        self.obs["projectiles"][0]["pos"] = [.5, 110, 7]
        self.assertTrue(self.choose(fire=[False, True])[1])
        self.obs.update(t=20.2, tick=404, projectiles=[])
        laser["charge"] = .75
        self.assertTrue(self.choose(fire=[False, True])[1])

    def test_deadline_exhaustion_returns_the_exact_ordinary_action(self):
        with patch("sentinel.impact_boost.time.perf_counter", side_effect=[0, 1]):
            self.assertEqual(self.choose(), ([1, 0], False))


if __name__ == "__main__":
    unittest.main()
