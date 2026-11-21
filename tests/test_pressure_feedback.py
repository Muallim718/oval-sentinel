"""Physical early-pressure feedback, not a match or house-bot simulator.

The same healthy player faces one lead-aiming gun pursuer and two slow,
tangential, aim-away mechs. All actors move, turn, and fire through ground_lab's
20 Hz physics; observations are issued at 10 Hz. A short, identical observation
history initializes real FOV tracking before either policy controls the player.
No hits, damage, targeting decisions, or baseline trigger choices are mocked.

Limits: synthetic flat terrain, approximate server ordering and enemy policy,
no secondary weapons/sounds/upgrades/air physics. The two distant actors are
deliberately nonattacking until the turning case; this tests that assumption's
causal consequences, not its frequency or correctness in scored matches.
"""
import copy
import math
import random
import sys
import time
import unittest

from test_bot import ROOT
sys.path.insert(0, str(ROOT/'tools'))
from ground_lab import Lab, DT, lead, wrapped
from sentinel.navigation import Navigator


class PressureFeedback(Lab):
    START = 5.0
    RADIUS = 110.0
    PASS_SPEED = 3.0
    ANGLE = math.atan2(54, 96)

    def __init__(self, turning=False, seed=11, seconds=18):
        super().__init__(ROOT, 'open_pursuit', seed, seconds)
        self.turning = turning
        self.turn_at = .8
        self.me = self.entity(0, [0, 0, 0], 1400)
        self.me['aim'] = [math.pi, 0]
        self.enemies = [self.entity(1, [-95, 0, 0], 1400)]
        self.enemies[0]['aim'] = [0, 0]
        for ident in (2, 3):
            position, velocity, yaw = self.passer_state(ident, self.START)
            enemy = self.entity(ident, position, 1400)
            enemy.update(vel=velocity, aim=[yaw, 0])
            self.enemies.append(enemy)
        self.entities = [self.me]+self.enemies
        for entity in self.entities:
            entity['_combat'] = entity['_spent'] = -100
        self.entity_rng[3] = random.Random(seed+1009*3)
        self.enemy_nav = {e['id']: Navigator(self.world, self.config['mech'])
                          for e in self.enemies}
        if hasattr(self.bot, 'salvage'):
            # ground_lab predates this helper: never leave its public-map World
            # attached while the rest of the bot sees the flat test arena.
            from sentinel.salvage import KillSalvage
            self.bot.salvage = KillSalvage(self.world, self.config)
        self.trace = []
        self.warm_visible = set()
        self.first_shot = None
        self.zone_damage = 0.0
        self.turn_started_yaw = None
        self.first_reactivation = None
        self.snapshot_2s = None
        self.actor_shots = {i: 0 for i in range(4)}
        self.initialized_history()

    @classmethod
    def passer_state(cls, ident, now):
        sign = 1 if ident == 2 else -1
        angle = sign*(cls.ANGLE+(now-cls.START)*cls.PASS_SPEED/cls.RADIUS)
        c, s = math.cos(angle), math.sin(angle)
        return ([cls.RADIUS*c, cls.RADIUS*s, 0],
                [-sign*cls.PASS_SPEED*s, sign*cls.PASS_SPEED*c, 0], angle)

    def initialized_history(self):
        """Both policies receive a legal east-to-west tracked-view history.

        This is an initial state, not a claim either policy chose that earlier
        camera sweep. The player turns at its actual 4 rad/s torso limit. Each
        passer first enters the true 120-degree FOV; the public five-second
        tracking memory then supplies current position/aim after it leaves FOV.
        Neither side fires or moves the player during this initialization.
        """
        for index in range(10):
            self.t = 4+index*.1
            self.me['aim'] = [min(math.pi, (self.t-4)*4), 0]
            for enemy in self.enemies[1:]:
                pos, vel, yaw = self.passer_state(enemy['id'], self.t)
                enemy.update(pos=pos, vel=vel, aim=[yaw, 0])
                center = [*pos[:2], enemy['stats']['height']/2]
                if self.visible(self.me, center):
                    self.warm_visible.add(enemy['id'])
            obs = self.observation(80+2*index)
            self.bot.remember(obs)
            if hasattr(self.bot, 'early_pressure'):
                self.bot.early_pressure.update(obs)
        self.me['aim'] = [math.pi, 0]
        for enemy in self.enemies[1:]:
            pos, vel, yaw = self.passer_state(enemy['id'], self.START)
            enemy.update(pos=pos, vel=vel, aim=[yaw, 0])
        self.t = self.START

    def observation(self, tick):
        obs = super().observation(tick)
        obs['alive'] = 16  # Thirteen other live slots outside this local scene.
        return obs

    def passer_action(self, enemy):
        if self.turning and enemy['id'] == 2 and self.t >= self.START+self.turn_at-1e-8:
            if self.turn_started_yaw is None:
                self.turn_started_yaw = enemy['aim'][0]
            origin = [*enemy['pos'][:2], enemy['stats']['muzzle_height']]
            target = [*self.me['pos'][:2], self.me['stats']['height']/2]
            aim = lead(origin, target, self.me['vel'], enemy['weapons'][0]['stats']['speed'])
            # Actual torso slew must first turn toward us. The gun then shoots
            # from that boresight, without guaranteed hits or free alignment.
            aligned = abs(wrapped(aim[0]-enemy['aim'][0])) < .1
            return dict(move=[0, 0], boost=False, aim=aim,
                        fire=[aligned, False], reload=enemy['weapons'][0]['ammo'] == 0)
        sign = 1 if enemy['id'] == 2 else -1
        x, y = enemy['pos'][:2]
        radius = math.hypot(x, y)
        c, s = x/radius, y/radius
        inward = (radius-self.RADIUS)*1.2
        velocity = [-sign*self.PASS_SPEED*s-inward*c,
                    sign*self.PASS_SPEED*c-inward*s]
        return dict(move=[v/enemy['stats']['walk_speed'] for v in velocity],
                    boost=False, aim=[math.atan2(y, x), 0], fire=[False, False], reload=False)

    def decision(self, tick):
        obs = self.observation(100+tick)
        start = time.perf_counter()
        action = self.bot.act(obs)
        self.metrics['max_decision_ms'] = max(self.metrics['max_decision_ms'],
            (time.perf_counter()-start)*1000)
        self.metrics['ignored_jump_requests'] += bool(action.get('jump'))
        pressure = getattr(self.bot, 'early_pressure', None)
        row = dict(t=round(self.t-self.START, 2), mode=self.bot.mode,
                   focus=getattr(self.bot, 'pressure_focus', None),
                   ignored=sorted(pressure.ignored) if pressure else [],
                   observed=[e['id'] for e in obs['mechs']],
                   pos=[round(v, 3) for v in self.me['pos'][:2]],
                   move=[round(v, 3) for v in action['move']],
                   boost=action['boost'], fire=action['fire'][0],
                   hp=round(self.me['hp'], 2), hunter_hp=round(self.enemies[0]['hp'], 2),
                   passer_range=round(math.dist(self.me['pos'], self.enemies[1]['pos']), 3),
                   passer_yaw=self.enemies[1]['aim'][0])
        if (pressure and self.turning and self.turn_started_yaw is not None and
                self.first_reactivation is None and not row['ignored']):
            self.first_reactivation = copy.deepcopy(row)
        self.trace.append(row)
        return action

    def run(self):
        action = {}
        for tick in range(round(self.seconds/DT)):
            self.t = self.START+tick*DT
            if tick % 2 == 0:
                action = self.decision(tick)
            actions = {0: action, 1: self.enemy_action(self.enemies[0], tick)}
            actions.update({e['id']: self.passer_action(e) for e in self.enemies[1:]})
            for entity in self.entities:
                if entity['hp'] <= 0:
                    continue
                self.move_entity(entity, actions[entity['id']])
                if not entity['in_zone']:
                    self.zone_damage += self.zone['dps']*DT
                shots = self.metrics['shots']
                emitted = self.next_bullet
                self.weapon(entity, actions[entity['id']])
                self.actor_shots[entity['id']] += self.next_bullet-emitted
                if self.metrics['shots'] > shots and self.first_shot is None:
                    self.first_shot = tick*DT
            self.projectiles()
            if self.world.line_clear(
                    [*self.enemies[0]['pos'][:2], self.enemies[0]['stats']['muzzle_height']],
                    [*self.me['pos'][:2], self.me['stats']['height']/2]):
                self.metrics['exposed_s'] += DT
            if self.snapshot_2s is None and tick*DT >= 1.95-1e-8:
                self.snapshot_2s = dict(hp=round(self.me['hp'], 2),
                    hunter_hp=round(self.enemies[0]['hp'], 2), shots=self.metrics['shots'],
                    damage_dealt=round(self.metrics['damage_dealt'], 2),
                    damage_taken=round(self.metrics['damage_taken'], 2),
                    pos=[round(v, 3) for v in self.me['pos'][:2]],
                    movement_m=round(self.metrics['movement_m'], 3))
            if self.me['hp'] <= 0 or self.enemies[0]['hp'] <= 0:
                break
        return dict(case='turning-passer' if self.turning else 'quiet-passers',
                    seed=self.hello['seed'], duration_s=round((tick+1)*DT, 2),
                    player_alive=self.me['hp'] > 0, hunter_alive=self.enemies[0]['hp'] > 0,
                    hp=round(max(0, self.me['hp']), 2), hunter_hp=round(max(0, self.enemies[0]['hp']), 2),
                    energy=round(self.me['energy'], 2), first_shot_s=self.first_shot,
                    zone_damage=self.zone_damage, warm_visible=sorted(self.warm_visible),
                    first_reactivation=self.first_reactivation,
                    turn_started_yaw=self.turn_started_yaw, at_2s=self.snapshot_2s,
                    actor_shots=dict(self.actor_shots),
                    **{k:round(v, 3) if isinstance(v, float) else v
                       for k, v in self.metrics.items()}, trace=self.trace)


class PressureFeedbackTests(unittest.TestCase):
    def test_real_tracked_passers_allow_fight_without_invented_hits(self):
        lab = PressureFeedback()
        result = lab.run()
        self.assertEqual(result['warm_visible'], [2, 3])
        self.assertEqual(result['trace'][0]['observed'], [1, 2, 3])
        self.assertEqual(result['trace'][0]['ignored'], [2, 3])
        self.assertEqual(result['trace'][0]['focus'], 1)
        self.assertEqual(result['trace'][0]['mode'], 'fight')
        self.assertGreater(result['shots'], 0)
        self.assertGreater(result['damage_dealt'], 0)
        self.assertEqual(result['zone_damage'], 0)
        self.assertEqual(result['ignored_jump_requests'], 0)
        self.assertGreater(result['movement_m'], 10)

    def test_actual_passer_turn_reactivates_crossfire_next_observation(self):
        lab = PressureFeedback(turning=True, seconds=2)
        result = lab.run()
        self.assertEqual(result['trace'][0]['ignored'], [2, 3])
        restored = result['first_reactivation']
        self.assertIsNotNone(restored)
        self.assertLessEqual(restored['t']-lab.turn_at, .1+1e-8)
        self.assertGreater(restored['passer_range'], 90)
        self.assertGreater(abs(wrapped(restored['passer_yaw']-result['turn_started_yaw'])), .3)
        self.assertEqual(restored['observed'], [1, 2, 3])
        self.assertIsNone(restored['focus'])
        self.assertIn(restored['mode'], ('evade', 'recover'))
        self.assertEqual(result['zone_damage'], 0)
        self.assertEqual(result['ignored_jump_requests'], 0)
        self.assertGreater(result['actor_shots'][2], 0)


if __name__ == '__main__':
    unittest.main()
