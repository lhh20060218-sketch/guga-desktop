"""Pure adapter for explicitly supplied, anonymized entity-tag observations.

Does not read processes/logs, infer local identity, or infer shop prices from COST.
The observer must supply controllers, phase and effective costs independently.
"""
from core.bg_agent import SnapshotError, validate_snapshot


def number(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return None


def remaining_health(tags):
    maximum, damage = number(tags.get("HEALTH")), number(tags.get("DAMAGE"))
    return max(0, maximum - damage) if maximum is not None and damage is not None else None


def available_gold(tags):
    values = [number(tags.get(k)) for k in ("RESOURCES", "TEMP_RESOURCES", "RESOURCES_USED")]
    if any(v is None for v in values):
        return None
    base, temporary, used = values
    return base + temporary - used if base + temporary >= used else None


def normalize_tag_observation(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("entities"), dict):
        raise SnapshotError("需要显式提供 entities 标签快照")
    local, shop = number(raw.get("local_controller")), number(raw.get("shop_controller"))
    if local is None or shop is None or local == shop:
        raise SnapshotError("需要分别确认本地玩家与商店控制器，不能猜测")
    entities = raw["entities"]
    if len(entities) > 500:
        raise SnapshotError("实体快照超过 500 项")
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in entities.items()):
        raise SnapshotError("实体 ID 必须为字符串，标签必须为对象")
    hero = entities.get(str(raw.get("hero_entity_id")), {})
    player = entities.get(str(raw.get("player_entity_id")), {})
    if number(hero.get("CONTROLLER")) != local or hero.get("CARDTYPE") != "HERO":
        raise SnapshotError("英雄身份/控制器尚未确认")
    if number(player.get("CONTROLLER")) != local:
        raise SnapshotError("资源所属玩家尚未确认")
    costs = raw.get("effective_costs", {})
    info = raw.get("card_info", {})
    if not isinstance(costs, dict) or not isinstance(info, dict):
        raise SnapshotError("effective_costs/card_info 必须为对象")
    state = {k: raw.get(k) for k in ("game_id", "revision", "patch", "source", "observed_at",
             "phase", "turn", "rules_profile", "economy_confirmed", "vanilla_transitions_confirmed",
             "refresh_cost", "upgrade_cost", "frozen") if k in raw}
    state.update(schema_version=1, gold=available_gold(player), health=remaining_health(hero),
                 armor=number(hero.get("ARMOR")), tier=number(hero.get("PLAYER_TECH_LEVEL")),
                 board=[], hand=[], shop=[], choices=[])
    for eid, tags in entities.items():
        kind = tags.get("CARDTYPE")
        if kind not in {"MINION", "SPELL"}:
            continue
        controller, zone = number(tags.get("CONTROLLER")), tags.get("ZONE")
        dest = ("board" if zone == "PLAY" else "hand" if zone == "HAND" else None) if controller == local else (
            "shop" if controller == shop and zone == "PLAY" else None)
        if dest is None:
            continue
        cid = tags.get("CARD_ID", "")
        if not isinstance(cid, str):
            raise SnapshotError("CARD_ID 必须为字符串")
        meta, price = info.get(cid, {}), costs.get(eid, {})
        if not isinstance(meta, dict) or not isinstance(price, dict):
            raise SnapshotError("实体元数据/费用必须为对象")
        state[dest].append({"entity_id": eid, "card_id": cid, "name": meta.get("name", cid or eid),
            "text": meta.get("text", ""), "kind": kind.lower(),
            "attack": number(tags.get("ATK")), "health": remaining_health(tags),
            "golden": number(tags.get("GOLDEN")) == 1,
            "effect": meta.get("effect", "unknown"), "races": meta.get("races", []),
            "keywords": meta.get("keywords", []), "currency": price.get("currency", "unknown"),
            "buy_cost": number(price.get("buy_cost")), "sell_value": number(price.get("sell_value")),
            "zone_position": number(tags.get("ZONE_POSITION"))})
    for zone in ("board", "hand", "shop"):
        state[zone].sort(key=lambda c: (c["zone_position"] is None, c["zone_position"] or 0, c["entity_id"]))
    state["field_sources"] = {"gold": "RESOURCES + TEMP_RESOURCES - RESOURCES_USED; missing => null",
        "health": "hero HEALTH - DAMAGE; missing => null", "identity": "explicit observer controller/entity mapping",
        "phase": "explicit observer phase", "costs": "effective_costs; never generic COST"}
    return validate_snapshot(state)
