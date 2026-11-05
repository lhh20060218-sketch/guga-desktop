"""Reconstruct demonstration contexts from allowlisted captured events.

Outputs reviewable CLIENT_OPTION selections, not fabricated buy/sell labels or
validated training data. Local controller must be explicitly supplied.
"""
import argparse
import json
from pathlib import Path


def reconstruct(events, local_controller):
    entities, options = {}, {}
    generation = None
    for event in events:
        kind = event["type"]
        if kind == "game_start":
            entities.clear()
            options.clear()
            generation = None
        elif kind == "entity":
            entity = entities.setdefault(str(event["entity_id"]), {})
            if "card_id" in event:
                entity["CARD_ID"] = event["card_id"]
            if "card_type" in event:
                entity["CARDTYPE"] = event["card_type"]
        elif kind == "player_entity":
            entities[str(event["entity_id"])] = {"CARDTYPE": "PLAYER", "CONTROLLER": event["controller"]}
        elif kind == "tag":
            entities.setdefault(str(event["entity_id"]), {})[event["tag"]] = event["after"]
        elif kind == "option_set":
            options.clear()
            generation = event["option_set_id"]
        elif kind == "option" and event.get("level") == "option":
            options[event["index"]] = {k:v for k,v in event.items()
                if k in ("index", "entity_id", "type_code", "error_code")}
        elif kind == "selected_option":
            selected = event.get("fields", {}).get("selectedOption")
            entity_ids = {str(o["entity_id"]) for o in options.values() if o.get("entity_id") is not None}
            visible = {eid:dict(e) for eid,e in entities.items()
                       if eid in entity_ids or e.get("CARDTYPE") == "GAME" or
                       (e.get("CONTROLLER") == local_controller and e.get("ZONE") in ("PLAY", "HAND"))}
            definition = options.get(selected)
            yield dict(schema=1, game_index=event["game_index"], log_time=event["log_time"],
                       source_byte_offset=event["source_byte_offset"], local_controller=local_controller,
                       option_set_id=generation, observed_entities=visible,
                       options=list(options.values()), selected=dict(event["fields"]),
                       selected_definition=definition,
                       evidence="client_SendOption_correlated_with_latest_DebugPrintOptions",
                       matched=definition is not None and event.get("option_set_id") == generation,
                       training_ready=False,
                       review_required=["local_identity_and_phase", "effective_costs",
                                        "option_targets_and_positions", "post_action_acknowledgement",
                                        "eventual_game_outcome_and_sample_quality"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("events")
    ap.add_argument("--local-controller", required=True, type=int)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = matched = 0
    with Path(args.events).open(encoding="utf-8") as source, output.open("x", encoding="utf-8") as target:
        for sample in reconstruct((json.loads(line) for line in source), args.local_controller):
            target.write(json.dumps(sample, ensure_ascii=True)+"\n")
            count += 1
            matched += sample["matched"]
    print(json.dumps(dict(samples=count, matched=matched, training_ready=False)))


if __name__ == "__main__":
    main()
