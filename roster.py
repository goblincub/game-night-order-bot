"""The game-night roster: who is ordering, to which address, and what food.

Each participant maps a name -> a saved DoorDash address -> an order. The order
is one of two modes:
  * reorder mode: `order_uuid` set  -> rebuild a past order
  * fresh mode:   `items_json` set  -> build a fresh order at store_id/menu_id

Addresses must already be saved on the account (dd-cli can't add them). The
roster lives in participants.json, which is gitignored (real address ids). Never
commit it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import dd_cli

ROSTER_PATH = Path(__file__).with_name("participants.json")

_DEMO_NAMES = ["Alice", "Bob", "Cara", "Dana", "Evan", "Finn"]


@dataclass
class Participant:
    name: str
    address_id: str
    address_label: str
    store_id: str = ""
    store_name: str = ""
    order_uuid: str = ""   # reorder mode
    menu_id: str = ""      # fresh mode
    items_json: str = ""   # fresh mode: JSON list of add-items entries

    def has_order(self) -> bool:
        return bool(self.order_uuid or self.items_json)


def load_roster() -> list[Participant]:
    if not ROSTER_PATH.exists():
        return []
    return [Participant(**p) for p in json.loads(ROSTER_PATH.read_text())]


def save_roster(people: list[Participant]) -> None:
    ROSTER_PATH.write_text(json.dumps([asdict(p) for p in people], indent=2))


def get(name: str) -> Participant | None:
    for p in load_roster():
        if p.name.lower() == name.lower():
            return p
    return None


def upsert(person: Participant) -> None:
    people = [p for p in load_roster() if p.name.lower() != person.name.lower()]
    people.append(person)
    save_roster(people)


def remove(name: str) -> bool:
    people = load_roster()
    kept = [p for p in people if p.name.lower() != name.lower()]
    save_roster(kept)
    return len(kept) != len(people)


def match_saved_address(query: str) -> dict | None:
    """Find a saved address whose text contains `query` (case-insensitive)."""
    q = query.strip().lower()
    for a in dd_cli.list_addresses():
        if q in a["printable"].lower():
            return a
    return None


def add_friend(name: str, address: dict) -> Participant:
    """Create/keep a friend linked to a saved address (order added later)."""
    existing = get(name)
    p = existing or Participant(name=name, address_id=address["address_id"],
                                address_label=address["printable"])
    p.address_id = address["address_id"]
    p.address_label = address["printable"]
    upsert(p)
    return p


def set_fresh_order(name: str, store_id: str, store_name: str, menu_id: str, entries: list[dict]) -> Participant:
    p = get(name)
    if not p:
        raise RuntimeError(f"No friend named {name}. Add them first.")
    p.store_id = store_id
    p.store_name = store_name
    p.menu_id = menu_id
    p.order_uuid = ""            # switch to fresh mode
    p.items_json = json.dumps(entries)
    upsert(p)
    return p


def build_demo_roster(size: int = 3) -> list[Participant]:
    """Demo roster from the payer's own saved addresses + recent reorderable orders."""
    addresses = dd_cli.list_addresses()
    orders = [o for o in dd_cli.order_history(limit=20) if o.reorderable]
    if not addresses or not orders:
        raise RuntimeError("Need at least one saved address and one reorderable order.")
    size = max(1, min(size, len(_DEMO_NAMES), len(addresses), len(orders)))
    people = [
        Participant(
            name=_DEMO_NAMES[i],
            address_id=addresses[i]["address_id"],
            address_label=addresses[i]["printable"],
            order_uuid=orders[i % len(orders)].order_uuid,
            store_id=orders[i % len(orders)].store_id,
            store_name=orders[i % len(orders)].store_name,
        )
        for i in range(size)
    ]
    save_roster(people)
    return people
