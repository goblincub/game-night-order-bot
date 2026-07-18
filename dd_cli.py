"""The one and only place that talks to `dd-cli`.

Spec §10: every DoorDash call goes through this module. No `subprocess` anywhere
else. Everything runs with `--json-output` and is parsed, never scraped.

v1 only needs the reorder path: history -> reorder -> preview -> (gated) submit.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# --- locating the binary ------------------------------------------------------
_DEFAULT = os.path.expanduser("~/.local/bin/dd-cli")
DD_CLI = _DEFAULT if os.path.exists(_DEFAULT) else "dd-cli"

# Append-only record of everything actually placed (spec §7). No addresses here.
PLACEMENT_LOG = Path(__file__).with_name("placements.jsonl")


class DDError(Exception):
    """A dd-cli call failed."""


class MoneyGateError(Exception):
    """An order exceeded a spending cap and was refused before any charge."""


# --- low-level runner ---------------------------------------------------------
def _run(args: list[str], timeout: int = 60, retries: int = 1) -> dict:
    """Run `dd-cli --json-output <args>` and return the structured payload.

    Retries once on a hard failure (the CLI is flaky, spec §10). Returns a dict;
    if the CLI printed non-JSON, wraps it as {"success": bool, "raw": str}.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                [DD_CLI, "--json-output", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
            continue

        out = (proc.stdout or "").strip()
        try:
            data = json.loads(out)
            return data.get("structuredContent", data)
        except json.JSONDecodeError:
            # Some commands emit non-JSON on the text path; treat exit code as truth.
            if proc.returncode == 0 and out:
                return {"success": True, "raw": out}
            last_exc = DDError(f"non-JSON output from {args}: {out[:200]} {proc.stderr[:200]}")
            time.sleep(2 * (attempt + 1))

    raise DDError(f"dd-cli {' '.join(args)} failed") from last_exc


# --- money helpers ------------------------------------------------------------
def money_to_cents(text: str) -> Optional[int]:
    """'$12.42' / '$1,234.56' -> cents. None if unparseable (fail safe upstream)."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*)\.(\d{2})", str(text))
    if not m:
        return None
    dollars = int(m.group(1).replace(",", ""))
    return dollars * 100 + int(m.group(2))


# --- data shapes --------------------------------------------------------------
@dataclass
class PastOrder:
    order_uuid: str
    store_id: str
    store_name: str
    order_date: str
    items: list[str]
    reorderable: bool


@dataclass
class Preview:
    cart_uuid: str
    store_name: str
    items: list[str]
    delivery_address: str
    total_cents: Optional[int]
    total_display: str
    fees: list[tuple[str, str]] = field(default_factory=list)  # (label, amount)


# --- addresses ----------------------------------------------------------------
def list_addresses() -> list[dict]:
    """All saved addresses: [{address_id, printable, city, zip, is_default}, ...]."""
    data = _run(["address", "list"])
    out = []
    for a in data.get("addresses", []) or []:
        out.append(
            {
                "address_id": str(a.get("address_id", "")),
                "printable": a.get("printable_address", ""),
                "city": a.get("city", ""),
                "zip": a.get("zip_code", ""),
                "is_default": bool(a.get("is_default")),
            }
        )
    return out


def get_default_address() -> Optional[dict]:
    """The currently-default saved address, or None."""
    for a in list_addresses():
        if a["is_default"]:
            return a
    return None


def set_default_address(address_id: str) -> None:
    """Change the account-wide default delivery address.

    This is a GLOBAL mutation — every open cart resolves to this address. The
    group engine flips it right before each order and MUST restore it after.
    """
    if not address_id:
        raise DDError("set_default_address: empty address_id")
    _run(["address", "set", "--address-id", address_id, "--yes"])


# --- read-only, free operations ----------------------------------------------
def order_history(limit: int = 10) -> list[PastOrder]:
    data = _run(["order", "history"])
    out: list[PastOrder] = []
    for o in data.get("orders", [])[:limit]:
        items = [f"{i.get('name')} x{i.get('quantity', 1)}" for i in o.get("items", [])]
        out.append(
            PastOrder(
                order_uuid=o.get("order_uuid", ""),
                store_id=str(o.get("store_id", "")),
                store_name=o.get("store_name", "?"),
                order_date=o.get("order_date", ""),
                items=items,
                reorderable=bool(o.get("is_reorderable")),
            )
        )
    return out


def list_open_carts() -> list[dict]:
    """All open/unsubmitted carts: [{store_id, store_name, cart_uuid}, ...]."""
    data = _run(["cart", "list"])
    out = []
    for c in data.get("carts", []) or []:
        out.append(
            {
                "store_id": str(c.get("store_id", "")),
                "store_name": c.get("store_name", "?"),
                "cart_uuid": c.get("cart_uuid", ""),
            }
        )
    return out


def clear_store_carts(store_id: str) -> int:
    """Delete any open cart at this store so a reorder starts clean.

    `order reorder` APPENDS to an existing open cart at the same store, which
    silently inflates totals across retries. Always clear first. Returns count
    deleted. Only touches the given store — never other stores' carts.
    """
    if not store_id:
        return 0
    deleted = 0
    for c in list_open_carts():
        if c["store_id"] == store_id and c["cart_uuid"]:
            cart_delete(c["cart_uuid"])
            deleted += 1
    return deleted


def reorder(order_uuid: str, store_id: str = "") -> str:
    """Create a fresh cart from a past order. Returns the new cart_uuid.

    Clears any existing open cart at `store_id` first (see clear_store_carts):
    otherwise reorder appends and the total inflates.
    """
    if store_id:
        clear_store_carts(store_id)
    data = _run(["order", "reorder", "--order-uuid", order_uuid])
    cart_uuid = data.get("cart_uuid")
    if not cart_uuid:
        raise DDError(f"reorder returned no cart_uuid: {data.get('message')}")
    return cart_uuid


def preview(cart_uuid: str) -> Preview:
    """Price a cart. Read-only, no charge. This is where fees become visible."""
    data = _run(["order", "preview", "--cart-uuid", cart_uuid])
    if not data.get("success", True):
        raise DDError(f"preview failed: {data.get('message')}")
    quote = data.get("quote", {}) or {}

    total_display = ""
    ntbt = quote.get("net_total_before_tip") or {}
    if isinstance(ntbt, dict):
        total_display = ntbt.get("display_string", "") or ""

    fees: list[tuple[str, str]] = []
    for li in quote.get("line_items", []) or []:
        label = li.get("label") or ""
        fm = li.get("final_money") or li.get("total_monetary_fields") or {}
        amt = fm.get("display_string", "") if isinstance(fm, dict) else ""
        if label:
            fees.append((label, amt))

    soc = quote.get("store_order_cart", {}) or {}
    items: list[str] = []
    for order in soc.get("orders", []) or []:
        for it in order.get("order_items", []) or []:
            name = (it.get("item") or {}).get("name") or it.get("name") or "?"
            qty = it.get("quantity", 1)
            items.append(f"{name} x{qty}")

    da = quote.get("delivery_address") or {}
    address = da.get("printable_address", "") if isinstance(da, dict) else ""
    store_name = (soc.get("store") or {}).get("name") or "?"

    return Preview(
        cart_uuid=cart_uuid,
        store_name=store_name,
        items=items,
        delivery_address=address,
        total_cents=money_to_cents(total_display),
        total_display=total_display or "?",
        fees=fees,
    )


def cart_delete(cart_uuid: str) -> None:
    try:
        _run(["cart", "delete", "--cart-uuid", cart_uuid])
    except DDError:
        pass  # best-effort cleanup


# --- the ONLY money-spending operation, fully gated (spec §7) -----------------
def submit(
    prev: Preview,
    *,
    dry_run: bool,
    max_per_order_cents: int,
    tip_cents: int = 0,
    scheduled_time: Optional[str] = None,
) -> dict:
    """Place an order. Refuses over the cap. In dry-run, never calls the CLI.

    Callers MUST have shown `prev` to the owner and gotten an explicit yes first.
    """
    # Gate 1: we must know the total. Unknown price -> refuse.
    if prev.total_cents is None:
        raise MoneyGateError("Could not read the order total from the preview — refusing to place.")

    # Gate 2: hard spending cap.
    if prev.total_cents > max_per_order_cents:
        raise MoneyGateError(
            f"Total {prev.total_display} exceeds cap "
            f"${max_per_order_cents/100:.2f} — refused, nothing placed."
        )

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cart_uuid": prev.cart_uuid,
        "store": prev.store_name,
        "total_cents": prev.total_cents,
        "total_display": prev.total_display,
        "dry_run": dry_run,
    }

    if dry_run:
        record["placed"] = False
        _append_log(record)
        return {"placed": False, "dry_run": True, "total_display": prev.total_display}

    # Log BEFORE the call returns (spec §7): if we crash mid-submit we still have a trace.
    _append_log(record)

    args = ["order", "submit", "--cart-uuid", prev.cart_uuid, "--yes"]
    if tip_cents:
        args += ["--tip-cents", str(tip_cents)]
    if scheduled_time:
        args += ["--scheduled-time", scheduled_time]

    result = _run(args, retries=0)  # submit is NOT idempotent — never auto-retry.
    return {"placed": True, "dry_run": False, "result": result, "total_display": prev.total_display}


def _append_log(record: dict) -> None:
    with PLACEMENT_LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
