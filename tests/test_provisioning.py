"""Secured free-resource acquisition and arming posture, not a match simulation."""
import copy
import math
import unittest
from test_bot import fixture, flat_world, rectangle
from sentinel.cover import firing_lane
from sentinel.memory import LootMemory
from sentinel.provisioning import Provisioner


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.hello, self.obs = fixture()
        self.me = self.obs["self"]
        self.me.update(pos=[-8, 18, 0], hp=1400, vel=[0, 0, 0])
        self.obs.update(alive=16, pickups=[], cubes=[], crates=[], events=[],
                        projectiles=[], mechs=[])
        self.world = flat_world([rectangle(-2, -40, 2, 40)])
        self.enemy = {"id": 1, "kind": "mech", "pos": [35, 0, 0],
                      "vel": [0, 0, 0], "hp": 1400, "max_hp": 1400,
                      "weapons": ["gun", "laser"]}
        self.loot = LootMemory()
        self.planner = Provisioner(self.world, self.hello["config"])
        self.circle = ([0, 0], 118)

    def add(self, category, item):
        self.loot.items[category][item["id"]] = (self.obs["t"], item)

    def weapon(self, pos=(-8, 28, 0)):
        return {"id": 8001, "kind": "laser", "pos": list(pos)}

    def choose(self, enemies=None, recovering=False):
        return self.planner.choose(self.obs, self.loot,
                                   [(e, 1) for e in (enemies or [self.enemy])],
                                   self.circle, recovering)

    def test_secondary_along_covered_side_is_allowed_with_enemy_under95m(self):
        self.add("pickups", self.weapon())
        plan = self.choose()
        self.assertEqual(plan.goal, (-8, 28))
        self.assertTrue(plan.arming)
        self.assertEqual(self.planner.state, "arming")

    def test_rounding_enemy_aborts_previously_certified_commitment(self):
        self.add("pickups", self.weapon())
        self.assertIsNotNone(self.choose())
        self.enemy["pos"] = [-35, 28, 0]
        self.assertIsNone(self.choose())
        self.assertIsNone(self.planner.plan)

    def test_second_open_enemy_vetoes_resource_behind_nearest_enemy_wall(self):
        self.add("pickups", self.weapon())
        exposed = {**self.enemy, "id": 2, "pos": [-90, 25, 0]}
        self.assertIsNone(self.choose([self.enemy, exposed]))

    def test_endpoint_cover_does_not_certify_exposed_middle_of_route(self):
        self.world = flat_world([rectangle(-2, -40, 2, -8), rectangle(-2, 8, 2, 40)])
        self.planner = Provisioner(self.world, self.hello["config"])
        self.me["pos"] = [-8, -25, 0]
        self.add("pickups", self.weapon((-8, 18, 0)))
        for point in (self.me["pos"], [-8, 18, 0]):
            self.assertFalse(firing_lane(self.world, self.hello["config"], point,
                                           self.me, self.enemy)[0])
        self.assertIsNone(self.choose())

    def test_gun_only_readiness_does_not_depend_on_pickup_memory(self):
        self.choose()
        self.assertTrue(self.planner.defer_duel(self.obs, self.enemy))
        self.add("pickups", self.weapon())
        self.choose()
        self.assertTrue(self.planner.defer_duel(self.obs, self.enemy))
        self.enemy["weapons"] = ["gun"]
        self.assertFalse(self.planner.defer_duel(self.obs, self.enemy))

    def test_weak_close_enemy_and_final_duel_override_arming_posture(self):
        self.add("pickups", self.weapon())
        self.choose()
        self.enemy.update(pos=[-25, 18, 0], hp=100)
        self.assertFalse(self.planner.defer_duel(self.obs, self.enemy))
        self.enemy["hp"] = 1400
        self.obs["alive"] = 2
        self.assertFalse(self.planner.defer_duel(self.obs, self.enemy))

    def test_hurt_bot_can_collect_free_covered_cube_without_crate_farming(self):
        self.me["hp"] = 500
        self.add("cubes", {"id": 5001, "pos": [-8, 25, 0]})
        self.add("crates", {"id": 1001, "pos": [-8, 21, 0], "hp": 300})
        plan = self.choose(recovering=True)
        self.assertEqual((plan.kind, plan.item_id), ("cube", 5001))
        self.assertFalse(plan.arming)

    def test_actual_equipment_receipt_and_initial_cooldown_gate_readiness(self):
        self.add("pickups", self.weapon())
        self.choose()
        self.me["weapons"][1] = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                                  "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.assertIsNone(self.choose())
        self.assertEqual(self.planner.state, "equipping")
        self.assertTrue(self.planner.defer_duel(self.obs, self.enemy))
        self.me["weapons"][1]["cooldown"] = 0
        self.choose()
        self.assertFalse(self.planner.defer_duel(self.obs, self.enemy))

    def test_opportunistic_receipt_gates_initial_but_not_later_firing_cooldowns(self):
        self.choose()  # no certified resource objective
        self.me["weapons"][1] = {"kind": "laser", "charge": 0, "cooldown": 1.65,
                                  "stats": copy.deepcopy(self.hello["config"]["weapons"]["laser"])}
        self.choose()
        self.assertEqual(self.planner.state, "equipping")
        self.assertTrue(self.planner.defer_duel(self.obs, self.enemy))
        self.me["weapons"][1]["cooldown"] = 0
        self.choose()
        self.me["weapons"][1]["cooldown"] = 1.2  # a later ordinary shot
        self.choose()
        self.assertNotEqual(self.planner.state, "equipping")
        self.assertFalse(self.planner.defer_duel(self.obs, self.enemy))

    def test_wall_or_roof_separation_is_not_a_valid_free_corridor(self):
        self.add("pickups", self.weapon((8, 18, 0)))
        self.assertIsNone(self.choose())
        self.loot.items["pickups"].clear()
        self.add("pickups", self.weapon((-8, 18, 20)))
        self.assertIsNone(self.choose())

    def test_zone_invalidates_resource_commitment(self):
        self.add("pickups", self.weapon())
        self.assertIsNotNone(self.choose())
        self.circle = ([35, 0], 25)
        self.assertIsNone(self.choose())

    def test_no_certification_budget_means_no_approved_plan(self):
        self.add("pickups", self.weapon())
        self.planner.SEARCH_SECONDS = 0
        self.assertIsNone(self.choose())

    def test_possible_npc_chase_lane_blocks_special_free_loot_override(self):
        self.add("pickups", self.weapon())
        self.obs["mechs"] = [{"id": 101, "kind": "npc", "pos": [-70, 25, 0]}]
        self.assertIsNone(self.choose())

    def test_imminent_projectile_crossing_blocks_special_free_loot_override(self):
        self.add("pickups", self.weapon())
        self.obs["projectiles"] = [{"id": 1201, "kind": "gun", "pos": [40, 18, 7],
                                    "vel": [-90, 0, 0]}]
        self.assertIsNone(self.choose())

    def test_gone_resource_does_not_preserve_commitment(self):
        self.add("pickups", self.weapon())
        self.assertIsNotNone(self.choose())
        self.loot.items["pickups"].clear()
        self.assertIsNone(self.choose())


if __name__ == "__main__":
    unittest.main()
