"""The game-night roster: who is ordering, to which address, and their 'usual'.

Because dd-cli can only deliver to addresses ALREADY saved on the account and
only to the account default (see docs/dd-cli-surface.md), each participant is a
(name -> saved address_id -> a past order to reorder) mapping. For testing we
map pretend friends to the payer's own saved addresses.

The roster lives in participants.json, which is gitignored (it references real
address ids). Never commit it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import dd_cli

ROSTER_PATH = Path(__file__).with_name("participants.json")

_DEMO_NAMES = ["Alice", "Bob", "Cara", "Dana", "Evan", "Finn"]


@dataclass
class Participant:
    name: str
    address_id: str
    address_label: str   # printable, for display only
    order_uuid: str
    store_id: str
    store_name: str


def load_roster() -> list[Participant]:
    if not ROSTER_PATH.exists():
        return []
    raw = json.loads(ROSTER_PATH.read_text())
    return [Participant(**p) for p in raw]


def save_roster(people: list[Participant]) -> None:
    ROSTER_PATH.write_text(json.dumps([asdict(p) for p in people], indent=2))


def build_demo_roster(size: int = 3) -> list[Participant]:
    """Auto-build a demo roster from the payer's own data (free, read-only reads).

    Pairs the first `size` distinct saved addresses with the `size` most recent
    reorderable past orders. Pretend friends named Alice, Bob, Cara, ...
    """
    addresses = dd_cli.list_addresses()
    orders = [o for o in dd_cli.order_history(limit=20) if o.reorderable]
    if not addresses or not orders:
        raise RuntimeError("Need at least one saved address and one reorderable order.")

    size = max(1, min(size, len(_DEMO_NAMES), len(addresses), len(orders)))
    people: list[Participant] = []
    for i in range(size):
        addr = addresses[i]
        order = orders[i % len(orders)]
        people.append(
            Participant(
                name=_DEMO_NAMES[i],
                address_id=addr["address_id"],
                address_label=addr["printable"],
                order_uuid=order.order_uuid,
                store_id=order.store_id,
                store_name=order.store_name,
            )
        )
    save_roster(people)
    return people
