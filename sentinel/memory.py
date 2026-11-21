"""Remember observed loot when looking away; never invent unseen objects."""
from .geometry import distance


class LootMemory:
    TTL = {"cubes": 25, "pickups": 60, "crates": 60}

    def __init__(self):
        self.items = {kind: {} for kind in self.TTL}

    def update(self, obs, world):
        now, me = obs["t"], obs["self"]
        for kind, ttl in self.TTL.items():
            visible = {item["id"]: item for item in obs[kind]}
            remembered = self.items[kind]
            for item_id, (seen_at, item) in list(remembered.items()):
                # A negative observation is evidence only nearby, on our level,
                # with an unobstructed view. Simply turning away is not evidence.
                close = distance(me["pos"], item["pos"]) < 7 and abs(me["pos"][2]-item["pos"][2]) < 4
                p = item["pos"]
                eye = [me["pos"][0], me["pos"][1], me["pos"][2]+me["stats"]["eye_height"]]
                if (now-seen_at > ttl or (close and item_id not in visible and
                        world.line_clear(eye, [p[0],p[1],p[2]+1]))):
                    remembered.pop(item_id, None)
            for item_id, item in visible.items():
                remembered[item_id] = (now, dict(item))
            for event in obs["events"]:
                if kind == "pickups" and event["type"] == "took":
                    remembered.pop(event["id"], None)
                if kind == "crates" and event["type"] == "hit" and event["target"] in remembered:
                    item_id = event["target"]
                    if item_id not in visible:
                        remembered[item_id][1]["hp"] -= event["amount"]
                    if remembered[item_id][1].get("hp", 1) <= 0:
                        remembered.pop(item_id, None)
            # Bound the state even in matches with unusually many cube drops.
            if len(remembered) > 256:
                newest = sorted(remembered, key=lambda k: remembered[k][0], reverse=True)[:256]
                self.items[kind] = {k: remembered[k] for k in newest}

    def get(self, kind):
        return [item for _, item in self.items[kind].values()]
