"""Post-kill healing/reload through actual gun and pickup feedback.

This is a limited 20 Hz ground model, not a house-bot or placement simulator.
Both policies inherit the same physically resolved final kill, actual dropped
cubes, visible crate and later gunner. The player policy controls every action
after the kill. There are no mocked hit receipts or accepted healing outcomes.
"""
import copy
import math
import unittest

from test_bot import ROOT, flat_world, rectangle
from test_opener_feedback import OpenerFeedback
from sentinel.combat import Combat
from sentinel.cover import CoverPlanner
from sentinel.movement import GroundSteering
from sentinel.navigation import Navigator
from ground_lab import DT, lead


class RefitFeedback(OpenerFeedback):
    START = 100.0
    HUNTER_START = 10.5
    SNAPSHOT = 11.0

    def __init__(self, hunter=True, seconds=15, crate_hp=300):
        super().__init__('crate', 11, seconds)
        self.case = 'refit'
        self.has_hunter = hunter
        self.world = flat_world([rectangle(60, 5, 65, 50)])
        self.bot.world = self.world
        self.bot.nav = Navigator(self.world, self.config['mech'])
        self.bot.combat = Combat(self.world, self.config)
        self.bot.cover = CoverPlanner(self.world, self.config)
        self.bot.motion = GroundSteering(self.world, self.config)
        if hasattr(self.bot, 'salvage'):
            from sentinel.salvage import KillSalvage
            self.bot.salvage = KillSalvage(self.world, self.config)
        if hasattr(self.bot, 'opener'):
            from sentinel.opener import Opener
            self.bot.opener = Opener(self.world, self.config)
        self.me = self.entity(0, [0, 0, 0], 910)
        self.me.update(kind='mech', aim=[0, 0])
        self.me['weapons'][0]['ammo'] = 3
        self.victim = self.entity(1, [-20, 0, 0], 45)
        self.victim.update(kind='mech', aim=[0, 0])
        self.enemies = [self.victim]
        self.hunter = None
        if hunter:
            self.hunter = self.entity(2, [75, 20, 0], 1400)
            self.hunter.update(kind='mech', aim=[-math.pi/2, 0])
            self.enemies.append(self.hunter)
        self.crates = [dict(id=1000, kind='crate', pos=[45, 0, 0], hp=crate_hp, max_hp=300,
                            stats=dict(radius=1.4, height=2.4), aim=[0, 0], vel=[0, 0, 0])]
        self.entities = [self.me]+self.enemies+self.crates
        self.enemy_nav = {e['id']: Navigator(self.world, self.config['mech']) for e in self.enemies}
        for entity in [self.me]+self.enemies:
            entity['_combat'] = self.START-.2
            entity['_spent'] = -100
        self.pickups = []
        self.loot = []
        self.trace = []
        self.damage_targets = []
        self.heal_events = []
        self.wave_snapshot = None
        self.rearm_snapshot = None
        self.first_hunter_seen = None
        self.first_refit_release = None
        self.crate_seen_before_kill = False
        self.kill_receipt = None
        self.initial_shots = 0
        self.initial_crate_hp = crate_hp
        self.establish_real_kill()

    def take_cube(self):
        super().take_cube()
        # This feedback compares real cube economies. Body/max-HP growth is
        # inherited; also apply the public capped damage gain to later rounds.
        multiplier = 1+self.config['cubes']['damage_per_cube']*min(
            self.me['cubes'], self.config['cubes']['stat_cap'])
        for weapon in self.me['weapons']:
            if weapon:
                weapon['stats'] = dict(weapon['stats'])
                weapon['stats']['damage'] = self.config['weapons'][weapon['kind']]['damage']*multiplier

    def damage(self, bullet, target):
        super().damage(bullet, target)
        if bullet['by'] == 0:
            self.damage_targets.append(dict(t=self.t-self.START, kind=target['kind'], id=target['id']))

    def establish_real_kill(self):
        # This initializes a possible post-fight state. The same actual FOV
        # sweep observes the crate, then the weakened hostile before the final
        # shot. Neither policy is credited with unobserved earlier damage.
        for index in range(9):
            self.t = 99+index*.1
            self.me['aim'] = [min(math.pi, index*.4), 0]
            obs = self.observation(-20+2*index)
            self.crate_seen_before_kill |= any(c['id'] == 1000 for c in obs['crates'])
            self.bot.remember(obs)
        origin = [*self.me['pos'][:2], self.me['stats']['muzzle_height']]
        target = [*self.victim['pos'][:2], self.victim['stats']['height']/2]
        controls = dict(aim=lead(origin, target, [0, 0, 0], 252), fire=[True, False])
        self.me['aim'] = list(controls['aim'])
        self.t = 99.85
        super(OpenerFeedback, self).weapon(self.me, controls)
        for _ in range(3):
            self.projectiles()
            if self.victim['hp'] <= 0:
                break
            self.t += DT
        self.kill_receipt = next((copy.deepcopy(event) for event in self.events
                                  if event['type'] == 'kill' and event['target'] == 1), None)
        if self.kill_receipt is None:
            raise AssertionError('final physical gun round did not kill its target')
        self.initial_shots = self.metrics['shots']
        self.kill_time = self.t
        self.t = self.START

    def observation(self, tick):
        obs = super().observation(tick)
        if getattr(self, 'hunter', None) and self.hunter['hp'] > 0 and any(
                e['id'] == self.hunter['id'] for e in obs['mechs']):
            if self.first_hunter_seen is None:
                self.first_hunter_seen = self.t-self.START
        return obs

    def hunter_action(self, tick):
        elapsed = self.t-self.START
        if elapsed < self.HUNTER_START:
            return dict(move=[0, 0], boost=False, aim=[-math.pi/2, 0], fire=[False, False])
        if self.hunter['pos'][1] > -12:
            move = [0, -1]
            origin = [*self.hunter['pos'][:2], self.hunter['stats']['muzzle_height']]
            target = [*self.me['pos'][:2], self.me['stats']['height']/2]
            return dict(move=move, boost=True, aim=lead(origin, target, self.me['vel'], 252),
                        fire=[self.world.line_clear(origin, target), False],
                        reload=self.hunter['weapons'][0]['ammo'] == 0)
        return self.enemy_action(self.hunter, tick)

    def run(self):
        controls = {}
        for tick in range(round(self.seconds/DT)):
            self.t = self.START+tick*DT
            if tick % 2 == 0:
                obs = self.observation(tick)
                controls = self.bot.act(obs)
                refit = getattr(self.bot, 'refit', None)
                active = bool(refit and refit.active)
                row = dict(t=round(tick*DT, 2), mode=self.bot.mode, refit=active,
                           reason=getattr(refit, 'reason', 'absent'),
                           hp=round(self.me['hp'], 2), max_hp=self.me['max_hp'],
                           ammo=self.me['weapons'][0]['ammo'], reload=self.me['weapons'][0]['reload'],
                           fire=controls['fire'][0], cubes=self.me['cubes'],
                           pos=list(self.me['pos']), observed=[e['id'] for e in obs['mechs']],
                           visible_projectiles=len(obs['projectiles']))
                self.trace.append(row)
                if refit and self.first_hunter_seen is not None and self.first_refit_release is None and not active:
                    self.first_refit_release = copy.deepcopy(row)
                self.metrics['ignored_jump_requests'] += bool(controls.get('jump'))
            old_hp = self.me['hp']
            super(OpenerFeedback, self).move_entity(self.me, controls)
            if self.me['hp'] > old_hp:
                self.heal_events.append(dict(t=tick*DT, amount=self.me['hp']-old_hp))
            super(OpenerFeedback, self).weapon(self.me, controls)
            if self.hunter is not None and self.hunter['hp'] > 0:
                enemy_controls = self.hunter_action(tick)
                super(OpenerFeedback, self).move_entity(self.hunter, enemy_controls)
                super(OpenerFeedback, self).weapon(self.hunter, enemy_controls)
            self.projectiles()
            self.collect(controls)
            self.body_collision |= not self.world.body_clear(*self.me['pos'],
                self.me['stats']['radius']-.001, self.me['stats']['height'], 0)
            if self.rearm_snapshot is None and tick*DT >= 3.0-1e-8:
                self.rearm_snapshot = dict(hp=round(self.me['hp'], 2),
                    ammo=self.me['weapons'][0]['ammo'], reload=self.me['weapons'][0]['reload'])
            if self.wave_snapshot is None and tick*DT >= self.SNAPSHOT-1e-8:
                self.wave_snapshot = dict(hp=round(self.me['hp'], 2), max_hp=self.me['max_hp'],
                    ammo=self.me['weapons'][0]['ammo'], reload=self.me['weapons'][0]['reload'],
                    cubes=self.me['cubes'], shots=self.metrics['shots']-self.initial_shots,
                    crate_hp=self.crates[0]['hp'], damage_taken=self.metrics['damage_taken'],
                    pos=list(self.me['pos']))
            if self.me['hp'] <= 0 or self.metrics['ignored_jump_requests'] or self.body_collision:
                break
            if self.has_hunter and (self.first_refit_release is not None or
                    (not hasattr(self.bot, 'refit') and self.first_hunter_seen is not None)):
                # The seeded crate may grant the reference a secondary. Its
                # post-arrival combat is outside this gun-only model: certify
                # the pre-wave state and defensive handoff, not a later duel.
                break
        return dict(initial_crate_hp=self.initial_crate_hp,
                    seconds=round((tick+1)*DT, 2), hp=round(max(0, self.me['hp']), 2),
                    max_hp=self.me['max_hp'], ammo=self.me['weapons'][0]['ammo'],
                    cubes=self.me['cubes'], healing=self.metrics['healing'],
                    first_heal=self.heal_events[0] if self.heal_events else None,
                    at_wave=self.wave_snapshot, at_3s=self.rearm_snapshot,
                    gear=[w['kind'] for w in self.me['weapons'] if w],
                    crate_seen_before_kill=self.crate_seen_before_kill,
                    actual_kill=self.kill_receipt, kill_time=self.kill_time,
                    damage_targets=self.damage_targets, optional_shots=self.metrics['shots']-self.initial_shots,
                    crate_hp=self.crates[0]['hp'], crate_weapon_roll=self.crate_weapon_roll,
                    first_hunter_seen=self.first_hunter_seen, first_refit_release=self.first_refit_release,
                    ignored_jumps=self.metrics['ignored_jump_requests'], body_collision=self.body_collision,
                    damage_taken=self.metrics['damage_taken'], damage_dealt=self.metrics['damage_dealt'],
                    trace=self.trace)


class RefitFeedbackTests(unittest.TestCase):
    def test_post_kill_quiet_reloads_and_respects_real_heal_delay(self):
        for crate_hp in (300, 90):
            with self.subTest(crate_hp=crate_hp):
                result = RefitFeedback(hunter=False, seconds=11.1, crate_hp=crate_hp).run()
                self.assertTrue(result['crate_seen_before_kill'])
                self.assertIsNotNone(result['actual_kill'])
                self.assertEqual(result['at_wave']['ammo'], 12)
                self.assertEqual(result['at_3s']['ammo'], 12)
                self.assertEqual(result['optional_shots'], 0)
                self.assertFalse(any(row['kind'] == 'crate' for row in result['damage_targets']))
                self.assertGreater(result['at_wave']['hp'], 1200)
                self.assertGreaterEqual(result['first_heal']['t']+RefitFeedback.START-result['kill_time'], 5-1e-8)
                self.assertAlmostEqual(result['first_heal']['amount'], 45*DT)
                self.assertEqual(result['ignored_jumps'], 0)
                self.assertFalse(result['body_collision'])

    def test_new_real_hunter_interrupts_refit(self):
        result = RefitFeedback().run()
        self.assertIsNotNone(result['first_hunter_seen'])
        self.assertIsNotNone(result['first_refit_release'])
        self.assertLessEqual(result['first_refit_release']['t']-result['first_hunter_seen'], .1+1e-8)
        self.assertGreater(result['first_refit_release']['visible_projectiles'], 0)
        self.assertEqual(result['ignored_jumps'], 0)
        self.assertFalse(result['body_collision'])


if __name__ == '__main__':
    unittest.main()
