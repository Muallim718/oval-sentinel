"""A fixed, between-wave opportunity to heal and reload after a real kill.

This policy asks the caller's existing cover planner to find shelter. It never
inventories a kill as loot, chooses movement, or grants permission to shoot.
"""
import math


class RefitCycle:
    HP_TARGET = .90
    RECOVERY_HP = .58
    MIN_SECONDS = 6.0
    MAX_SECONDS = 18.0
    CLOSE_HUNTER = 55.0

    def __init__(self, config):
        self.config = config
        self.active = False
        self.started = self.deadline = -1.0
        self.last_dealt = self.last_taken = -100.0
        self.last_tick = None
        self.victims = []
        self.reason = "no between-wave refit"

    def cancel(self, reason="ordinary policy regained control"):
        self.active = False
        self.reason = reason

    @staticmethod
    def _gun(me):
        return next((weapon for weapon in me["weapons"]
                     if weapon and weapon["kind"] == "gun"), None)

    @staticmethod
    def _distance(a, b):
        return math.hypot(a[0]-b[0], a[1]-b[1])

    def _start(self, obs, victims):
        me, now = obs["self"], obs["t"]
        ratio = me["hp"]/me["max_hp"]
        gun = self._gun(me)
        thin_magazine = gun and gun.get("ammo", 0) <= gun["stats"]["mag"]/3
        if (ratio < self.RECOVERY_HP or not me["in_zone"] or obs["alive"] <= 2 or
                (ratio >= self.HP_TARGET and not thin_magazine)):
            return
        mech = me["stats"]
        missing = max(0, self.HP_TARGET*me["max_hp"]-me["hp"])
        healing = mech["regen_delay"]+missing/mech["regen_per_s"] if missing else 0
        reload_time = gun["stats"].get("reload", 2.4) if thin_magazine else 0
        duration = min(self.MAX_SECONDS, max(self.MIN_SECONDS, max(healing, reload_time)+3))
        self.active, self.started, self.deadline = True, now, now+duration
        self.victims = list(victims)[-4:]
        self.reason = "secure a bounded quiet window after a verified mech kill"

    def update(self, obs):
        marker = (obs["tick"], obs["t"])
        if marker == self.last_tick:
            return
        self.last_tick = marker
        me, now = obs["self"], obs["t"]
        victims = [event["target"] for event in obs["events"]
                   if event["type"] == "kill" and isinstance(event.get("target"), int) and
                   0 <= event["target"] < 16 and event["target"] != me["id"]]
        if victims:
            self.last_dealt = now
            if not self.active:
                self._start(obs, victims)
            else:
                self.victims = list(dict.fromkeys(self.victims+victims))[-4:]
        new_attacker = False
        for event in obs["events"]:
            if event["type"] == "hit" and event.get("amount", 0) > 0:
                self.last_dealt = now
            elif event["type"] == "damaged" and event.get("amount", 0) > 0:
                self.last_taken = now
                # A killed hunter's final airborne rounds still delay regen,
                # but are not evidence that the next wave has arrived.
                if event.get("by") not in self.victims:
                    new_attacker = True
        if not self.active:
            return
        gun = self._gun(me)
        rearmed = gun is None or (gun.get("reload", 0) <= 0 and
                                 gun.get("ammo", 0) >= gun["stats"]["mag"]*.65)
        if now >= self.deadline:
            self.cancel("fixed refit deadline reached")
        elif me["hp"] < me["max_hp"]*self.RECOVERY_HP:
            self.cancel("ordinary severe-damage recovery owns the mech")
        elif not me["in_zone"]:
            self.cancel("storm escape owns the mech")
        elif obs["alive"] <= 2:
            self.cancel("the final opponent takes priority")
        elif new_attacker:
            self.cancel("fresh damage proves the quiet window has ended")
        elif me["hp"] >= me["max_hp"]*self.HP_TARGET and rearmed:
            self.cancel("health and magazine are ready for the next wave")

    def _enemies(self, obs, threats):
        enemies = {enemy["id"]: enemy for enemy, confidence in threats
                   if confidence >= .25 and enemy.get("kind") == "mech" and
                   enemy["id"] not in self.victims}
        enemies.update({enemy["id"]: enemy for enemy in obs["mechs"]
                        if enemy.get("kind") == "mech" and enemy["id"] not in self.victims})
        return list(enemies.values())

    def _incoming(self, obs):
        """Conservative .7s physical crossing test for a partial-reload guard."""
        me = obs["self"]
        for projectile in obs["projectiles"]:
            p, velocity = projectile["pos"], projectile["vel"]
            dx, dy = p[0]-me["pos"][0], p[1]-me["pos"][1]
            vx, vy = velocity[0]-me["vel"][0], velocity[1]-me["vel"][1]
            t = max(0, min(.7, -(dx*vx+dy*vy)/(vx*vx+vy*vy or 1)))
            mortar = projectile["kind"] == "mortar"
            radius = me["stats"]["radius"]+(8 if mortar else .6)
            if math.hypot(dx+vx*t, dy+vy*t) > radius:
                continue
            z = p[2]+velocity[2]*t
            if mortar:
                z -= self.config["weapons"]["mortar"]["gravity"]*t*t/2
            if me["pos"][2]-2 < z < me["pos"][2]+me["stats"]["height"]+2:
                return True
        return False

    def choose(self, obs, threats, *, sheltered=False, zone_safe=True,
               ordinary_recovery=False):
        self.update(obs)
        if not self.active:
            return False
        me = obs["self"]
        enemies = self._enemies(obs, threats)
        close = [enemy for enemy in enemies if self._distance(me["pos"], enemy["pos"]) < 140]
        if ordinary_recovery:
            self.cancel("ordinary recovery already owns the quiet period")
        elif not zone_safe:
            self.cancel("predicted storm escape takes priority")
        elif any(self._distance(me["pos"], enemy["pos"]) < self.CLOSE_HUNTER for enemy in enemies):
            self.cancel("a hunter is too close for a between-wave pause")
        elif not sheltered and (len(close) >= 2 or any(
                enemy.get("charging") and self._distance(me["pos"], enemy["pos"]) <=
                self.config["weapons"]["laser"]["range"] for enemy in enemies)):
            self.cancel("exposed crossfire or a charging laser ends the pause")
        elif not sheltered and self._incoming(obs):
            self.cancel("an incoming shot requires ordinary defensive control")
        elif not sheltered and any(enemy.get("kind") == "npc" and
                self._distance(me["pos"], enemy["pos"]) < self.config["npc"]["aggro_range"]
                for enemy in obs["mechs"]):
            self.cancel("an active nearby drone requires defensive control")
        return self.active

    def should_reload(self, obs, sheltered, threats):
        """Permit an early reload only when its uninterruptible window is safe."""
        self.update(obs)
        if not self.active:
            return False
        me, now = obs["self"], obs["t"]
        gun = self._gun(me)
        if (gun is None or gun.get("reload", 0) > 0 or
                gun.get("ammo", 0) >= gun["stats"]["mag"]*.65 or
                now+gun["stats"].get("reload", 2.4)+.1 >= self.deadline or
                now-self.last_taken < .6 or self._incoming(obs)):
            return False
        if any(enemy.get("kind") == "npc" and self._distance(me["pos"], enemy["pos"]) <
               self.config["npc"]["deaggro_range"] for enemy in obs["mechs"]):
            return False
        enemies = self._enemies(obs, threats)
        if any(self._distance(me["pos"], enemy["pos"]) < self.CLOSE_HUNTER for enemy in enemies):
            return False
        if sheltered:
            return True
        if now-max(self.last_dealt, self.last_taken) < .75:
            return False
        # An exposed reload needs a genuinely quiet field, including remembered
        # hunters that could enter gun/laser reach before the magazine is ready.
        reach = max(self.config["weapons"]["gun"]["range"],
                    self.config["weapons"]["laser"]["range"])
        return not any(self._distance(me["pos"], enemy["pos"]) < reach+20 for enemy in enemies)
