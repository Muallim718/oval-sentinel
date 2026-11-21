"""Opening missions and their resource confirmations, not a placement test."""
import math
import unittest
from unittest.mock import patch

from test_bot import fixture, flat_world, rectangle
from sentinel.geometry import angle_error
from sentinel.opener import Opener


class OpenerTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.config = self.hello["config"]
        self.world = flat_world()
        self.me = self.obs["self"]
        self.me.update(pos=[-70, 0, 0], vel=[0, 0, 0], hp=1400, max_hp=1400,
                       energy=100, cubes=0, grounded=True, in_zone=True, aim=[0, 0])
        self.me["weapons"][0].update(ammo=12, reload=0, cooldown=0)
        self.obs.update(t=0, tick=0, mechs=[], events=[], projectiles=[], crates=[],
                        cubes=[], pickups=[], drops=[])
        self.opener = Opener(self.world, self.config)
        self.circle = ([0, 0], 118)

    def choose(self, recovering=False, threats=()):
        return self.opener.choose(self.obs, threats, self.circle, recovering=recovering)

    def advance(self, now, events=()):
        self.obs.update(t=now, tick=round(now*20), events=list(events))

    def crate(self, hp=300):
        self.obs["crates"] = [{"id": 1001, "pos": [-50, 0, 0], "hp": hp}]
        return self.obs["crates"][0]

    def npc(self):
        target = {"id": 101, "kind": "npc", "pos": [-45, 0, 0], "vel": [0, 0, 0],
                  "hp": 350, "max_hp": 350}
        self.obs["mechs"] = [target]
        return target

    def test_fast_viable_floor_weapon_beats_distant_farming(self):
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [-50, 0, 0]}]
        self.obs["crates"] = [{"id": 1001, "pos": [0, 0, 0], "hp": 300}]
        mission = self.choose()
        self.assertEqual((mission.kind, mission.target_id), ("weapon", 8001))
        self.assertIsNone(mission.exclusive_target)
        self.assertEqual(mission.goal, (-50, 0, 0))

    def test_real_open_route_to_100_meter_secondary_is_available_without_hidden_45_meter_gate(self):
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [30, 0, 0]}]
        mission = self.choose()
        self.assertIsNotNone(mission)
        self.assertEqual(mission.goal, (30, 0, 0))
        self.assertTrue(mission.sprint)
        self.assertTrue(self.world.walk_clear(self.me["pos"], mission.waypoint))

    def test_crate_mission_pins_actual_target_instead_of_opportunistic_shooting(self):
        target = self.crate()
        mission = self.choose()
        self.assertEqual(mission.kind, "crate")
        self.assertEqual(mission.exclusive_target["id"], target["id"])
        self.assertEqual(mission.goal, (-59, 0, 0))
        self.assertGreaterEqual(mission.goal[0]-self.me["pos"][0], 0)

    def test_visible_crate_hp_does_not_double_count_its_hit_event(self):
        target = self.crate()
        self.choose()
        target["hp"] = 255
        self.advance(.3, [{"type": "hit", "target": 1001, "weapon": "gun", "amount": 45}])
        mission = self.choose()
        self.assertEqual(mission.exclusive_target["hp"], 255)

    def test_confirmed_crate_kill_switches_to_real_cube_id_then_completes_on_pickup(self):
        self.crate(hp=30)
        self.choose()
        self.obs["crates"] = []
        self.obs["cubes"] = [{"id": 5001, "pos": [-50, 0, 0]}]
        self.advance(.3, [{"type": "hit", "target": 1001, "weapon": "gun", "amount": 45}])
        mission = self.choose()
        self.assertEqual((mission.kind, mission.target_id), ("collect", 5001))
        self.assertIsNone(mission.exclusive_target)
        self.assertEqual(mission.goal, (-50, 0, 0))
        self.me.update(pos=[-50, 0, 0], cubes=1)
        self.obs["cubes"] = []
        self.advance(.6, [{"type": "pickup", "cubes": 1}])
        self.assertIsNone(self.choose())
        self.assertEqual(self.opener.completed, 1)

    def test_floor_weapon_completion_requires_receipt_or_actual_equipment(self):
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [-50, 0, 0]}]
        self.choose()
        self.assertEqual(self.opener.completed, 0)
        self.me["pos"] = [-50, 0, 0]
        self.me["weapons"][1] = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                                  "stats": self.config["weapons"]["laser"]}
        self.obs["pickups"] = []
        self.advance(1, [{"type": "took", "id": 8001, "kind": "laser", "slot": 1}])
        self.assertIsNone(self.choose())
        self.assertEqual(self.opener.completed, 1)

    def test_expected_npc_retaliation_does_not_abort_its_short_two_cube_mission(self):
        target = self.npc()
        mission = self.choose()
        self.assertEqual((mission.kind, mission.target_id), ("npc", 101))
        self.me["hp"] = 1375
        target["hp"] = 260
        self.advance(.5, [{"type": "damaged", "weapon": "npc", "by": 101,
                            "amount": 25}])
        self.assertEqual(self.choose().exclusive_target["id"], 101)
        self.assertEqual(self.opener.current["expected_cubes"], 2)

    def test_other_attacker_or_recovery_immediately_returns_control(self):
        self.npc()
        self.choose()
        self.advance(.5, [{"type": "damaged", "weapon": "gun", "by": 1, "amount": 45}])
        self.me["hp"] = 1355
        self.assertIsNone(self.choose())
        self.assertIsNone(self.opener.current)
        self.advance(4)
        self.assertIsNone(self.choose(recovering=True))

    def test_known_close_hunter_or_charging_laser_vetoes_farming(self):
        self.crate()
        enemy = {"id": 1, "kind": "mech", "pos": [0, 0, 0], "vel": [0, 0, 0],
                 "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}
        self.obs["mechs"] = [enemy]
        self.assertIsNone(self.choose())
        self.opener = Opener(self.world, self.config)
        self.world.bounds = {"minX": -300, "maxX": 300, "minY": -300, "maxY": 300}
        enemy.update(pos=[130, 0, 0], weapons=["gun", "laser"], charging=True)
        self.assertIsNone(self.choose())

    def test_roof_resource_unsafe_zone_or_airborne_start_is_not_a_ground_opener(self):
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [-50, 0, 20]}]
        self.assertIsNone(self.choose())
        self.obs["pickups"][0]["pos"][2] = 0
        self.circle = ([80, 0], 20)
        self.advance(.1)
        self.assertIsNone(self.choose())
        self.circle = ([0, 0], 118)
        self.me.update(grounded=False, pos=[-70, 0, .5])
        self.advance(.2)
        self.assertIsNone(self.choose())

    def test_missing_gun_cancels_an_active_attack_without_crashing(self):
        self.crate()
        self.choose()
        self.me["weapons"][0] = None
        self.advance(.1)
        self.assertIsNone(self.choose())
        self.assertIsNone(self.opener.current)

    def test_actual_checked_detour_waypoint_does_not_walk_through_a_wall(self):
        self.world = flat_world([rectangle(-45, -25, -40, 25)])
        self.opener = Opener(self.world, self.config)
        target = {"id": 8001, "kind": "laser", "pos": [-20, 0, 0]}
        self.opener.loot.items["pickups"][8001] = (0, target)
        mission = None
        for step in range(10):
            self.advance(step*.1)
            mission = self.choose()
            if mission:
                break
        self.assertIsNotNone(mission)
        self.assertFalse(self.world.walk_clear(self.me["pos"], target["pos"]))
        self.assertTrue(self.world.walk_clear(self.me["pos"], mission.waypoint,
                                              self.me["stats"]["radius"]+.3,
                                              self.me["stats"]["height"]))

    def test_nearby_wrong_side_path_endpoint_does_not_certify_an_inaccessible_tail(self):
        self.world = flat_world([rectangle(-.1, -100, .1, 100)])
        self.opener = Opener(self.world, self.config)
        self.me["pos"] = [-30, 0, 0]
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [3, 0, 0]}]
        self.opener.nav.search_done = True
        with patch.object(self.opener.nav, "plan", return_value=[(-3, 0, 0)]):
            self.assertIsNone(self.choose())

    def test_stalled_or_lost_target_mission_does_not_chase_forever(self):
        self.npc()
        self.choose()
        self.obs["mechs"] = []
        self.advance(.5)
        self.assertIsNone(self.choose())
        self.opener = Opener(self.world, self.config)
        self.obs["pickups"] = [{"id": 8001, "kind": "laser", "pos": [-50, 0, 0]}]
        self.choose()
        self.advance(3.6)
        self.assertIsNone(self.choose())

    def test_quiet_scan_completes_a_sweep_quickly_but_stops_after_damage(self):
        turned = 0
        for step in range(17):
            self.advance(step*.1)
            yaw = self.opener.scan_yaw(self.obs, [])
            self.assertIsNotNone(yaw)
            change = angle_error(yaw, self.me["aim"][0])
            self.assertLessEqual(abs(change), self.me["stats"]["turn_rate"]*.1)
            turned += change
            self.me["aim"][0] = yaw  # Two legal 20 Hz torso steps reach this command.
        self.assertGreater(turned, math.tau)
        self.advance(1.8, [{"type": "damaged", "weapon": "gun", "by": 1, "amount": 45}])
        self.assertIsNone(self.opener.scan_yaw(self.obs, []))

    def test_after_opening_period_no_loot_or_route_work_is_performed(self):
        self.crate()
        self.choose()
        self.advance(60)
        with patch.object(self.opener, "update", side_effect=AssertionError("late loot work")):
            self.assertIsNone(self.choose())
            self.assertIsNone(self.opener.scan_yaw(self.obs, []))
        self.assertIsNone(self.opener.current)


if __name__ == "__main__":
    unittest.main()
