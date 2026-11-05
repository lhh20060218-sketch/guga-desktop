"""Read-only, allowlisted Power.log events for demonstrations and replay.

No account names, account IDs, raw lines, model calls or client input. The
processed PowerTaskList stream is canonical so GameState duplicates are not
counted twice. Unknown tags remain unknown, not invented zeros.
"""
import re

TAGS = set("""CARDTYPE ZONE ZONE_POSITION CONTROLLER PLAYER_ID HERO_ENTITY
HEALTH DAMAGE ARMOR ATK TECH_LEVEL PLAYER_TECH_LEVEL PLAYER_LEADERBOARD_PLACE
RESOURCES TEMP_RESOURCES RESOURCES_USED CURRENT_PLAYER TURN STEP NEXT_STEP STATE
PLAYSTATE COST GOLDEN TAUNT DIVINE_SHIELD WINDFURY MEGA_WINDFURY POISONOUS
VENOMOUS REBORN FROZEN FREE_REFRESH_REMAINING BACON_DUMMY_PLAYER
BACON_CURRENT_COMBAT_PLAYER_ID BACON_SHOPKEEPER_ID BACON_SHOPKEEPER
BACON_IS_COMBAT_PHASE BACON_IN_COMBAT BACON_IN_COMBAT_PHASE BACON_PLAYER_TRIPLES
TAG_LAST_KNOWN_COST_IN_HAND BACON_TAVERN_UPGRADE_COST HERO_POWER HEROPOWER
HERO_POWER_DISABLED NUM_TURNS_IN_PLAY BACON_TRIPLE_UPGRADE_MINION_ID
COPIED_FROM_ENTITY_ID CREATOR LINKED_ENTITY HAS_ACTIVATE_POWER
BACON_IS_SHOP_ENTITY NEXT_OPPONENT_PLAYER_ID TAG_SCRIPT_DATA_NUM_1 TAG_SCRIPT_DATA_NUM_2
GAME_TYPE GAMETYPE FORMAT_TYPE BACON_GLOBAL_TURN""".split())
_REF = r"(?:\[[^\]]*\bid=(\d+)[^\]]*\]|(\d+)|GameEntity)"
_TAG = re.compile(r"\btag=(\w+) value=([A-Za-z0-9_-]+)")


def _number_or_word(value):
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"[A-Z][A-Z_0-9]*", value):
        return value
    return None


def _entity_ref(text):
    text = text.removeprefix("UNKNOWN ENTITY ")
    if text.startswith("GameEntity"):
        return 0
    if text.startswith("["):
        # UNKNOWN ENTITY names can themselves contain [cardType=INVALID].
        # The numeric id + zone fields identify the outer entity reference.
        match = re.search(r"\bid=(\d+)\s+zone=", text)
        return int(match.group(1)) if match else None
    match = re.match(_REF, text)
    return int(match.group(1) or match.group(2)) if match else None


class EventParser:
    def __init__(self):
        self.entities = {}
        self.pending_entity = None
        self.game_index = 0
        self.revision = 0
        self.player_aliases = {}  # Private RAM only; never serialized.
        self.option_set_id = None
        self.options = {}

    def feed(self, line):
        # Parse only one power stream; complementary local choices come from
        # GameState. Never retain raw line text or free-form values.
        stamp = re.search(r"\b(\d{2}:\d{2}:\d{2}\.\d+)\b", line)
        base = {"log_time": stamp.group(1) if stamp else None, "game_index": self.game_index}
        if "GameState.DebugPrintGame()" in line:
            player = re.search(r"\bPlayerID=(\d+),? PlayerName=(.+?)\s*$", line)
            if player:
                if len(self.player_aliases) > 32:
                    self.player_aliases.clear()
                self.player_aliases[player.group(2)] = int(player.group(1))
                return [dict(base, type="player_mapping", controller=int(player.group(1)))]
            build = re.search(r"\bBuildNumber=(\d+)", line)
            mode = re.search(r"\bGameType=(GT_[A-Z_]+)", line)
            if build:
                return [dict(base, type="client_build", build=int(build.group(1)))]
            if mode:
                return [dict(base, type="game_mode", mode=mode.group(1))]
            return []
        if "GameState.SendOption()" in line:
            fields = {k: int(v) for k, v in re.findall(
                r"\b(selectedOption|selectedSubOption|selectedTarget|selectedPosition)=(-?\d+)", line)}
            definition = self.options.get(fields.get("selectedOption"))
            return [dict(base, type="selected_option", fields=fields,
                         option_set_id=self.option_set_id, option=definition)] if fields else []
        if "GameState.DebugPrintOptions()" in line:
            generation = re.search(r"\(\) - id=(\d+)\s*$", line)
            if generation:
                self.option_set_id = int(generation.group(1))
                self.options.clear()
                return [dict(base, type="option_set", option_set_id=self.option_set_id)]
            option = re.search(r"\b(option|subOption|target) (\d+)", line)
            if not option:
                return []
            record = dict(base, type="option", level=option.group(1), index=int(option.group(2)),
                          option_set_id=self.option_set_id)
            for field in ("type", "error"):
                match = re.search(r"\b"+field+r"=([A-Z_0-9]+)", line)
                if match:
                    record[field+"_code"] = match.group(1)
            match = re.search(r"\bmainEntity=(.*)", line)
            if match:
                record["entity_id"] = _entity_ref(match.group(1))
            if record["level"] == "option":
                self.options[record["index"]] = {k:v for k,v in record.items()
                    if k in ("index", "entity_id", "type_code", "error_code")}
            return [record]
        if "GameState.DebugPrintEntitiesChosen()" in line:
            # Keep explicit numeric references only. Free-form choice text is excluded.
            ids = [int(x) for x in re.findall(r"\bid=(\d+)\b", line)]
            return [dict(base, type="chosen_entities", entity_ids=ids)] if ids else []
        if "PowerTaskList.DebugPrintPower()" not in line:
            return []
        if "CREATE_GAME" in line:
            self.entities.clear()
            self.pending_entity = None
            self.option_set_id = None
            self.options.clear()
            self.game_index += 1
            return [dict(base, type="game_start", game_index=self.game_index)]
        match = re.search(r"GameEntity EntityID=(\d+)", line)
        if match:
            eid = int(match.group(1))
            self.pending_entity = eid
            self.entities[eid] = {"CARDTYPE": "GAME"}
            return [dict(base, type="entity", entity_id=eid, card_type="GAME")]
        match = re.search(r"Player EntityID=(\d+) PlayerID=(\d+)", line)
        if match:
            eid, controller = map(int, match.groups())
            self.pending_entity = eid
            self.entities[eid] = {"CARDTYPE": "PLAYER", "CONTROLLER": controller}
            return [dict(base, type="player_entity", entity_id=eid, controller=controller)]
        if "FULL_ENTITY" in line or "SHOW_ENTITY" in line or "CHANGE_ENTITY" in line:
            match = re.search(r"\bID=(\d+) CardID=([A-Za-z0-9_]*)", line)
            if match:
                eid, card = int(match.group(1)), match.group(2)
            else:
                ref = re.search(r"(?:\bEntity=|\bUpdating )(.+)", line)
                cid = re.search(r"\bCardID=([A-Za-z0-9_]*)", line)
                eid, card = (_entity_ref(ref.group(1)) if ref else None), (cid.group(1) if cid else "")
            if eid is None:
                self.pending_entity = None
                return []
            self.pending_entity = eid
            self.entities.setdefault(eid, {})["CARD_ID"] = card
            return [dict(base, type="entity", entity_id=eid, card_id=card)]
        if "BLOCK_START" in line:
            self.pending_entity = None
            kind = re.search(r"BlockType=(\w+)", line)
            source = re.search(r"\bEntity=(.*)", line)
            target = re.search(r"\bTarget=(.*)", line)
            return [dict(base, type="block", block_type=kind.group(1) if kind else None,
                         source_id=_entity_ref(source.group(1)) if source else None,
                         target_id=_entity_ref(target.group(1)) if target else None)]
        match = _TAG.search(line)
        if not match:
            if not re.search(r" -\s+tag=", line):
                self.pending_entity = None
            return []
        tag, text = match.groups()
        if tag not in TAGS and not tag.isdecimal():
            return []
        value = _number_or_word(text)
        if value is None:
            return []
        if "TAG_CHANGE" in line:
            ref = re.search(r"\bEntity=(.*)", line)
            eid = _entity_ref(ref.group(1)) if ref else None
            if eid is None and ref:
                alias = ref.group(1).split(" tag=", 1)[0].strip()
                controller = self.player_aliases.get(alias)
                matches = [k for k,e in self.entities.items() if e.get("CARDTYPE") == "PLAYER"
                           and e.get("CONTROLLER") == controller] if controller is not None else []
                if len(matches) == 1:
                    eid = matches[0]
            self.pending_entity = None
            if eid == 0:
                games = [k for k, e in self.entities.items() if e.get("CARDTYPE") == "GAME"]
                eid = games[0] if len(games) == 1 else None
        elif re.search(r" -\s+tag=", line):
            eid = self.pending_entity
        else:
            return []
        if eid is None:
            return [dict(base, type="unresolved_tag", tag=tag, value=value)]
        entity = self.entities.setdefault(eid, {})
        previous = entity.get(tag)
        if previous == value:
            return []
        entity[tag] = value
        self.revision += 1
        return [dict(base, type="tag", entity_id=eid, tag=tag, before=previous, after=value,
                     revision=self.revision)]

    def snapshot(self):
        # This is observed data only. No inferred local controller, phase,
        # effective prices, zero DAMAGE defaults or training action labels.
        return {"game_index": self.game_index, "revision": self.revision,
                "entities": {str(k): dict(v) for k, v in self.entities.items()}}
