"""Read-only review of HDT's Chinese combat records; estimates are not outcomes.

Text records have no stable game ID or combat timestamps. Groups below are
source-file segments, never an automatic join to Power.log or training labels.
"""
import re
import xml.etree.ElementTree as ET

HEADER = re.compile(r"^第(\d+)回合[，,](.+?)\s+VS\s+(.+)$")
ROUND = re.compile(r"^第(\d+)回合[，,]")
MINION = re.compile(r"(.+?)[（(](\d+)-(\d+)[）)](?:[；;]|$)")
OUTCOMES = {"赢": "win", "平": "tie", "输": "loss"}


def _board(text):
    """Empty is observed empty; malformed/absent is unknown, not empty."""
    text = text.strip()
    if not text:
        return []
    matches = list(MINION.finditer(text))
    if not matches or MINION.sub("", text).strip():
        return None
    return [dict(name=m[1].strip(), attack=int(m[2]), health=int(m[3])) for m in matches]


def _estimate(line):
    count = re.search(r"模拟(\d+)次", line)
    pairs = re.findall(r"(\d+(?:\.\d+)?)%\s*(抬走对面|被抬走|赢|平|输)", line)
    fields = {"抬走对面": "opponent_lethal", "被抬走": "own_lethal", **OUTCOMES}
    probabilities = {fields[label]: float(value) / 100 for value, label in pairs}
    issues = []
    if not all(k in probabilities for k in OUTCOMES.values()):
        issues.append("missing_win_tie_loss")
    elif abs(sum(probabilities[k] for k in OUTCOMES.values()) - 1) > .002:
        issues.append("probabilities_do_not_sum_to_one")
    if any(not 0 <= p <= 1 for p in probabilities.values()):
        issues.append("probability_out_of_range")
    for sub, parent in (("own_lethal", "loss"), ("opponent_lethal", "win")):
        if sub in probabilities and parent in probabilities and probabilities[sub] > probabilities[parent] + .002:
            issues.append("lethal_exceeds_" + parent)
    return dict(simulations=int(count[1]) if count else None,
                probabilities=probabilities, issues=issues)


def _actual(line):
    match = re.search(r"实际结果[：:]\s*(赢|平|输)", line)
    if not match:
        return None
    damage = re.search(r"(?:打了对面|被对面打了)(\d+)", line)
    alive = False if "我被抬走了" in line else True if "我还活着" in line else None
    return dict(outcome=OUTCOMES[match[1]], damage=int(damage[1]) if damage else None,
                damage_direction="dealt" if "打了对面" in line else "received" if "被对面打了" in line else None,
                own_alive=alive)


def parse_hdt_records(text):
    groups, current, record = [], None, None
    ignored = 0

    def new_group(reason):
        return dict(group_id=len(groups) + 1, boundary_evidence=reason,
                    client_game_id=None, timestamps_available=False, power_log_join="unmatched",
                    placements=[], rounds=[])

    def flush():
        nonlocal record
        if record is None:
            return
        # Deduplicate repeated combat headers only when the observed boards,
        # round and heroes match. Different estimates/outcomes remain visible.
        identity = ("round", "own_hero", "opponent_hero", "own_board", "opponent_board", "missing_combat")
        previous = next((r for r in current["rounds"]
                         if all(r.get(k) == record.get(k) for k in identity)), None)
        if previous is None:
            current["rounds"].append(record)
        else:
            previous["source_lines"].extend(record["source_lines"])
            previous["duplicate_headers"] += 1
            for field in ("estimates", "actuals"):
                for item in record[field]:
                    if item not in previous[field]:
                        previous[field].append(item)
        record = None

    partial_line = bool(text and not text.endswith(("\n", "\r")))
    source_lines = text.splitlines()
    for number, line in enumerate(source_lines, 1):
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        header, round_match = HEADER.match(line), ROUND.match(line)
        if partial_line and number == len(source_lines) and not round_match:
            # The producer may be in the middle of appending a board or result.
            # Do not promote a truncated line into an observed empty board.
            continue
        if round_match:
            flush()
            turn = int(round_match[1])
            reset = current and current["rounds"] and turn < max(r["round"] for r in current["rounds"])
            if current is None or current.get("ended") or reset:
                reason = "explicit_previous_end" if current and current.get("ended") else "round_decreased_unverified" if reset else "file_start"
                current = new_group(reason)
                groups.append(current)
            record = dict(round=turn, own_hero=header[2].strip() if header else None,
                          opponent_hero=header[3].strip() if header else None,
                          own_board=None, opponent_board=None, estimates=[], actuals=[],
                          missing_combat=header is None, source_lines=[number], duplicate_headers=0)
        elif line.startswith("游戏结束"):
            flush()
            if current:
                placement = re.search(r"第(\d+)名", line)
                if placement and int(placement[1]) not in current["placements"]:
                    current["placements"].append(int(placement[1]))
                current["end_line"] = number
                # Keep the ended group until another round starts: repeated
                # end lines may correct a result without creating fake games.
                current["ended"] = True
        elif record:
            record["source_lines"].append(number)
            if line.startswith("我方随从："):
                record["own_board"] = _board(line.split("：", 1)[1])
            elif line.startswith("对方随从："):
                record["opponent_board"] = _board(line.split("：", 1)[1])
            elif line.startswith("模拟结果"):
                item = _estimate(line)
                if item not in record["estimates"]:
                    record["estimates"].append(item)
            elif line.startswith("实际结果"):
                item = _actual(line)
                if item and item not in record["actuals"]:
                    record["actuals"].append(item)
            else:
                ignored += 1
        else:
            ignored += 1
    flush()
    return dict(schema=1, source="HDT_local_combat_text", groups=groups,
                ignored_lines=ignored, trailing_partial_line_ignored=partial_line,
                training_ready=False, contains_raw_lines=False,
                limitations=["Groups have no client game IDs or combat timestamps",
                             "No automatic alignment with Power.log",
                             "Missing rounds, boards and odds remain unknown",
                             "Simulation engine/rule coverage is not verified",
                             "No action quality or causality inferred from a combat result"])


def load_card_metadata(path, card_ids):
    """Select only needed card metadata from the installed HDT XML cache."""
    cards = {}
    for _, entity in ET.iterparse(path, events=("end",)):
        if entity.tag != "Entity":
            continue
        card_id = entity.get("CardID")
        if card_id in card_ids:
            tags = {t.get("name"): t for t in entity.findall("Tag")}
            cards[card_id] = dict(
                name=tags["CARDNAME"].findtext("zhCN") if "CARDNAME" in tags else None,
                text_template=tags["CARDTEXT"].findtext("zhCN") if "CARDTEXT" in tags else None,
                pool_subsets=[k.removeprefix("BACON_SUBSET_") for k, t in tags.items()
                              if k and k.startswith("BACON_SUBSET_") and t.get("value") == "1"])
        entity.clear()
    return cards


def snapshot_review(snapshot, local_controller, metadata):
    """Annotate an observed snapshot without claiming it is a stable board."""
    entities = snapshot.get("entities", {})
    players = [(eid, e) for eid, e in entities.items()
               if e.get("CARDTYPE") == "PLAYER" and e.get("CONTROLLER") == local_controller]
    player = players[0][1] if len(players) == 1 else {}
    hero = entities.get(str(player.get("HERO_ENTITY")), {})
    board = []
    for eid, entity in entities.items():
        if entity.get("CONTROLLER") != local_controller or entity.get("ZONE") != "PLAY" or entity.get("CARDTYPE") != "MINION":
            continue
        card_id = entity.get("CARD_ID")
        board.append(dict(entity_id=eid, card_id=card_id, position=entity.get("ZONE_POSITION"),
                          attack=entity.get("ATK"), health_tag=entity.get("HEALTH"),
                          damage_tag=entity.get("DAMAGE"), metadata=metadata.get(card_id),
                          script_data_1=entity.get("TAG_SCRIPT_DATA_NUM_1"),
                          script_data_2=entity.get("TAG_SCRIPT_DATA_NUM_2")))
    board.sort(key=lambda x: (x["position"] is None, x["position"] or 0, str(x["entity_id"])))
    required = ("RESOURCES", "TEMP_RESOURCES", "RESOURCES_USED")
    gold = player[required[0]] + player[required[1]] - player[required[2]] if all(isinstance(player.get(k), int) for k in required) else None
    health = hero["HEALTH"] - hero["DAMAGE"] if all(isinstance(hero.get(k), int) for k in ("HEALTH", "DAMAGE")) else None
    return dict(local_controller=local_controller, game_index=snapshot.get("game_index"),
                round=player.get("TURN"), tavern_tier=player.get("PLAYER_TECH_LEVEL"),
                playstate=player.get("PLAYSTATE"), gold=gold, health=health, armor=hero.get("ARMOR"),
                hero_card_id=hero.get("CARD_ID"), hero_metadata=metadata.get(hero.get("CARD_ID")),
                board=board, phase_and_stability_confirmed=False,
                plugin_win_rate=None, plugin_join="unmatched", training_ready=False)


def render_review(report):
    rows = ["# 咕嘎对局观察与胜率记录", "",
            "插件模拟概率与实际结果分别列出。文本记录没有局 ID 和战斗时间，尚未与 Power.log 自动对齐。", ""]
    power = report.get("separate_power_snapshot")
    if power:
        hero = (power.get("hero_metadata") or {}).get("name") or power.get("hero_card_id") or "未知"
        rows += ["## Power.log 独立快照", "",
                 f"采样文件时间（UTC）：{power.get('source_modified_at', '未知')}。",
                 f"观察值：{hero}，玩家回合 {power['round']}，酒馆 {power['tavern_tier']} 级，血量 {power['health']}，护甲 {power['armor']}，剩余金币 {power['gold']}。", "",
                 "下表是观察到的 PLAY 随从；阶段及场面稳定性未确认，不能直接视为最终招募阵容。攻血标签保留日志原值，缺少伤害标签时不推算剩余血量。", "",
                 "| 位置 | 卡牌 | CardID | 攻击标签 / 血量标签 | 实体 |",
                 "|---|---|---|---|---|"]
        for minion in power["board"]:
            name = (minion.get("metadata") or {}).get("name") or minion.get("card_id") or "未知"
            rows.append(f"| {minion['position']} | {name} | {minion['card_id']} | {minion['attack']} / {minion['health_tag']} | {minion['entity_id']} |")
        rows += ["", "该快照尚未匹配到同场插件胜率；卡牌来自本机缓存，缓存版本与客户端 Build 的一致性尚未验证。", ""]
    for group in report["groups"]:
        rows += [f"## 文本片段 {group['group_id']}", "",
                 f"边界依据：`{group['boundary_evidence']}`；记录名次：{group['placements'] or '未知'}。", "",
                 "| 回合 | 我方英雄 / 对手 | 我方阵容 | 模拟胜 / 平 / 负 | 实际结果 |",
                 "|---|---|---|---|---|"]
        for combat in group["rounds"]:
            board = combat["own_board"]
            army = "未知" if board is None else "；".join(f"{m['name']} {m['attack']}/{m['health']}" for m in board) or "空场"
            odds = "缺失"
            if combat["estimates"]:
                e = combat["estimates"][-1]
                odds = " / ".join(f"{100*e['probabilities'][k]:g}%" if k in e["probabilities"] else "?" for k in ("win", "tie", "loss"))
                odds += f"（{e['simulations']} 次；未校验规则覆盖）"
                if len(combat["estimates"]) > 1 or e["issues"]:
                    odds += " ⚠ 有不同估计或数据异常，见 JSON"
            actual = "缺失"
            if combat["actuals"]:
                a = combat["actuals"][-1]
                actual = {"win": "胜", "tie": "平", "loss": "负"}[a["outcome"]]
                if a["damage"] is not None:
                    actual += f"，{'打出' if a['damage_direction']=='dealt' else '受到'} {a['damage']} 点伤害"
                if a["own_alive"] is False:
                    actual += "，被淘汰"
                if len(combat["actuals"]) > 1:
                    actual += " ⚠ 结果冲突，见 JSON"
            cells = [str(combat["round"]), f"{combat['own_hero'] or '?'} / {combat['opponent_hero'] or '?'}", army, odds, actual]
            rows.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
        rows.append("")
    rows += ["缺失记录不表示玩家没有操作。重复的相同阵容记录已合并；不同估计与冲突结果保留在 JSON。",
             "被抬走概率属于负率的子集，不能再与胜／平／负相加。单次实际结果也不能证明某个操作正确或错误。", ""]
    return "\n".join(rows)
