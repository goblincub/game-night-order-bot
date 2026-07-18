"""The game-night engine: preview everyone, then place serially.

Why serial: dd-cli delivers only to the account default address, resolved live
(docs/dd-cli-surface.md). So we flip the default to each person's address, place
their order, then move on — and ALWAYS restore the original default afterward.

Timing: every order is submitted with the same `scheduled_time`, so they land
together instead of scattered — no stagger engine needed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import dd_cli
import menu_order
from roster import Participant


def _build_cart(p: Participant) -> str:
    """Build this person's cart, reorder-mode or fresh-mode. Returns cart_uuid."""
    if p.order_uuid:
        return dd_cli.reorder(p.order_uuid, p.store_id)
    if p.items_json:
        dd_cli.clear_store_carts(p.store_id)
        return menu_order.add_to_cart(p.store_id, p.menu_id, json.loads(p.items_json))
    raise dd_cli.DDError(f"{p.name} has no order set")


@dataclass
class PersonResult:
    name: str
    store_name: str
    items: list[str] = field(default_factory=list)
    address: str = ""
    total_cents: Optional[int] = None
    total_display: str = "?"
    ok: bool = True
    placed: bool = False
    deliverable: bool = True
    note: str = ""


def _restore(original: Optional[dict]) -> None:
    if original and original.get("address_id"):
        try:
            dd_cli.set_default_address(original["address_id"])
        except dd_cli.DDError:
            pass


def preview_all(people: list[Participant]) -> tuple[list[PersonResult], int]:
    """Build + price each person's order at their own address. No charge.

    Restores the account default when done. Returns (results, grand_total_cents).
    """
    original = dd_cli.get_default_address()
    results: list[PersonResult] = []
    grand = 0
    try:
        for p in people:
            try:
                dd_cli.set_default_address(p.address_id)
                cart = _build_cart(p)
                prev = dd_cli.preview(cart)
                dd_cli.cart_delete(cart)  # don't hold carts across address flips
                # Sanity: the preview address should be this person's address.
                want = p.address_label.split(",")[0].strip()
                mismatch = want and want not in prev.delivery_address
                note = ""
                if not prev.deliverable:
                    note = f"🚫 {prev.delivery_note}"
                elif mismatch:
                    note = "⚠️ address mismatch"
                results.append(
                    PersonResult(
                        name=p.name,
                        store_name=prev.store_name,
                        items=prev.items,
                        address=prev.delivery_address,
                        total_cents=prev.total_cents,
                        total_display=prev.total_display,
                        ok=True,
                        deliverable=prev.deliverable,
                        note=note,
                    )
                )
                grand += prev.total_cents or 0
            except dd_cli.DDError as exc:
                results.append(
                    PersonResult(name=p.name, store_name=p.store_name, ok=False, note=str(exc))
                )
    finally:
        _restore(original)
    return results, grand


def place_all(
    people: list[Participant],
    *,
    dry_run: bool,
    max_per_order_cents: int,
    max_per_night_cents: int,
    scheduled_time: Optional[str] = None,
    tip_cents: int = 0,
) -> tuple[list[PersonResult], int]:
    """Place everyone's order serially. Enforces caps BEFORE placing anything.

    Spec §7: exceed a per-person or per-night cap -> hard fail, place NOTHING.
    """
    # 1) Price everything first (this restores the default itself).
    previews, grand = preview_all(people)

    # 2a) Deliverability — refuse the whole night if anyone is out of range.
    undeliverable = [r for r in previews if r.ok and not r.deliverable]
    if undeliverable:
        names = ", ".join(f"{r.name} ({r.note})" for r in undeliverable)
        raise dd_cli.MoneyGateError(f"DoorDash can't deliver to: {names}. Nothing placed.")

    # 2b) Cap checks up front — refuse the whole night if anything is over.
    over = [r for r in previews if r.ok and (r.total_cents or 0) > max_per_order_cents]
    if over:
        names = ", ".join(f"{r.name} ({r.total_display})" for r in over)
        raise dd_cli.MoneyGateError(
            f"Over the per-person cap ${max_per_order_cents/100:.2f}: {names}. Nothing placed."
        )
    if grand > max_per_night_cents:
        raise dd_cli.MoneyGateError(
            f"Group total ${grand/100:.2f} exceeds the night cap "
            f"${max_per_night_cents/100:.2f}. Nothing placed."
        )

    # 3) Place serially, restoring the default afterward no matter what.
    original = dd_cli.get_default_address()
    results: list[PersonResult] = []
    try:
        for p in people:
            try:
                dd_cli.set_default_address(p.address_id)
                cart = _build_cart(p)
                prev = dd_cli.preview(cart)
                res = dd_cli.submit(
                    prev,
                    dry_run=dry_run,
                    max_per_order_cents=max_per_order_cents,
                    tip_cents=tip_cents,
                    scheduled_time=scheduled_time,
                )
                if dry_run:
                    dd_cli.cart_delete(cart)  # nothing placed; don't leave it open
                results.append(
                    PersonResult(
                        name=p.name,
                        store_name=prev.store_name,
                        items=prev.items,
                        address=prev.delivery_address,
                        total_cents=prev.total_cents,
                        total_display=prev.total_display,
                        ok=True,
                        placed=bool(res.get("placed")),
                        note="dry run" if dry_run else "placed",
                    )
                )
            except (dd_cli.DDError, dd_cli.MoneyGateError) as exc:
                results.append(
                    PersonResult(name=p.name, store_name=p.store_name, ok=False, note=str(exc))
                )
    finally:
        _restore(original)
    return results, grand
