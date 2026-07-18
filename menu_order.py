"""Order fresh food from a searched restaurant (not just reorder history).

The tricky parts, learned by testing the real CLI:
- Restaurants near an address: `search --lat --lng`; skip `is_link_out` stores
  (those can't be ordered through the CLI).
- Item options live under `restaurant-item-details` -> item.extras[], each group
  has min_num_options and options[] (option_id + name + price, possibly nested).
- Required options MUST be filled or the add fails. We auto-pick the cheapest
  required choice(s) per group, recursively.
- `cart add-items` is flaky, so we verify the item actually landed and retry.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import dd_cli


@dataclass
class Store:
    store_id: str
    name: str
    distance: str
    eta: str


@dataclass
class MenuItem:
    item_id: str
    name: str
    price: float


def search_stores(query: str, lat: float, lng: float, limit: int = 6) -> list[Store]:
    """Orderable (non-link-out) restaurants near a coordinate."""
    data = dd_cli._run(
        ["search", "--query", query, "--lat", str(lat), "--lng", str(lng), "--limit", str(limit)]
    )
    out = []
    for s in data.get("stores", []) or []:
        if s.get("is_link_out"):
            continue
        out.append(
            Store(
                store_id=str(s.get("store_id", "")),
                name=s.get("name", "?"),
                distance=s.get("distance", ""),
                eta=s.get("delivery_time", ""),
            )
        )
    return out


def get_menu(store_id: str) -> tuple[str, list[MenuItem]]:
    """Return (menu_id, items). Items are the top-level menu entries."""
    data = dd_cli._run(["menu", "--store-id", store_id])
    menu_id = str(data.get("menu_id", ""))

    def walk(o):
        if isinstance(o, dict):
            if o.get("item_id"):
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    seen, items = set(), []
    for it in walk(data.get("items", [])):
        iid = it.get("item_id")
        if iid and iid not in seen:
            seen.add(iid)
            items.append(MenuItem(item_id=iid, name=it.get("name", "?"), price=it.get("price") or 0.0))
    return menu_id, items


def _fill_required(extras) -> list[dict]:
    """Recursively auto-pick the cheapest required option(s) for each group."""
    nested = []
    for g in extras or []:
        minn = g.get("min_num_options") or 0
        if minn < 1:
            continue  # optional group — leave it out
        choices = sorted(g.get("options", []) or [], key=lambda o: o.get("price", 0) or 0)[:minn]
        for c in choices:
            entry = {"id": c["option_id"], "name": c.get("name", ""), "quantity": 1}
            sub = _fill_required(c.get("extras"))
            if sub:
                entry["options"] = sub
            nested.append(entry)
    return nested


def build_item_entry(store_id: str, menu_id: str, item: MenuItem) -> dict:
    """An items-json entry for `cart add-items`, with required options filled in."""
    entry = {"item_id": item.item_id, "item_name": item.name, "quantity": 1}
    det = dd_cli._run(
        ["restaurant-item-details", "--store-id", store_id, "--menu-id", menu_id, "--item-id", item.item_id]
    )
    nested = _fill_required((det.get("item") or {}).get("extras"))
    if nested:
        entry["nested_options"] = nested
    return entry


def add_to_cart(store_id: str, menu_id: str, entries: list[dict], cart_uuid: str = "") -> str:
    """Add items and VERIFY they landed (cart add-items is flaky). Returns cart_uuid.

    Retries the whole add once after a short wait if the preview can't be priced.
    """
    args = ["cart", "add-items", "--store-id", store_id, "--menu-id", menu_id,
            "--items-json", json.dumps(entries)]
    if cart_uuid:
        args += ["--cart-uuid", cart_uuid]
    for attempt in range(2):
        data = dd_cli._run(args)
        cu = data.get("cart_uuid") or cart_uuid
        if cu:
            try:
                prev = dd_cli.preview(cu)
                if prev.total_cents:  # priced == items really landed
                    return cu
            except dd_cli.DDError:
                pass
        time.sleep(8)  # flakiness backoff before one retry
    if not cu:
        raise dd_cli.DDError("Could not add items to a cart (DoorDash kept dropping them).")
    return cu
