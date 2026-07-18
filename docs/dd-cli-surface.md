# dd-cli surface — Phase 0 recon

**Tool:** `dd-cli v0.2.0` (darwin-arm64), installed at `~/.local/bin/dd-cli`, signed in.
**Method:** `--help` on every relevant command + one empirical address test (read-only /
no-charge). No orders were ever submitted.

This document answers the six Phase 0 questions from the spec (§11). The load-bearing
one (Q2) was resolved by experiment, not inference.

---

## TL;DR

- **Q1 Scheduled delivery — YES.** `--scheduled-time` on `order preview` and `order submit`.
- **Q2 Per-order address — NO, and worse than "no default override":** the delivery address
  is resolved **live from the account default** at preview/submit time and is **not**
  snapshotted onto a cart. Proven empirically (see below). The "six held carts, one per
  address" model is dead.
- **Q3 ETA in preview — YES**, under `quote.delivery_availability`.
- **Q4 Cart lifecycle — multiple carts, but one per store.**
- **Q5 Placing — `order submit --cart-uuid <id> --yes`**, charges immediately, **not idempotent**.
- **Q6 Failure at placement time — untested** (needs a live deliberate-failure run in Phase 2).
- **Bonus blocker:** there is **no `address add`** — the `address` group is `list` + `set` only.
  You can only choose among addresses already saved on the account.

---

## Command tree (top level)

```
address                  list | set  (NO add/remove)
build-grocery-list       assemble a multi-store grocery cart in one shot
cart                     add-items | show | remove-item | delete | list
find-items               search items within a retail/grocery store
find-nearby-stores       non-restaurant stores within 16 mi
item-details             retail/grocery item detail
login                    sign in (keychain-backed)
menu                     restaurant menu  (returns nothing for link-out stores)
order                    history | preview | submit | reorder | status | receipt | checkout-url
payment-method           list saved payment methods
promo                    store promotions
restaurant-item-details  restaurant item detail
search                   nearby restaurants (needs --lat/--lng; falls back to Cupertino)
store-details            store metadata
```

---

## Q1 — Scheduled delivery: YES

`--scheduled-time TEXT` exists on **both** `order preview` and `order submit`:

- ISO 8601. **Naive strings default to America/Los_Angeles** — always pass a UTC suffix
  (e.g. `2026-07-18T01:10:00Z`) to avoid a timezone-ambiguity bug.
- This largely **collapses spec §4's stagger engine**: instead of computing `place_at`
  per order and re-checking ETAs, set the same target delivery window on every order.
- Caveat still to verify live: whether every merchant honors the requested window, and
  window granularity. Keep the stagger engine as a documented fallback but do **not**
  build it first.

## Q2 — Per-order delivery address: NO (resolved by experiment)

From `order preview --help`:

> *"The cart must already have a delivery address and a payment method attached. The
> default consumer address is used; there is no CLI option to override it today."*

The only address control is `address set --address-id <id> --yes`, which changes the
**account-wide default**.

### The experiment (the important part)

Question the help didn't answer: is the address **snapshotted onto the cart** at build
time, or **resolved live** from the current default?

1. Set default → **Address A** (one saved address).
2. Built a cart (`order reorder` of a past order).
3. `order preview` on that cart → delivery address = **A**. ✅
4. Set default → **Address B** (a different saved address) via `address set`.
5. `order preview` on the **same `cart-uuid`** → delivery address = **B**. ❌

**Conclusion: the address is read live from the account default. Open carts carry no
address of their own.** Flipping the default retargets every open cart at once.

### Consequences

- **Dead:** "build six carts up front, each bound to a friend's address, hold, place on a
  stagger" (spec §4/§9). All open carts share one mutable global.
- **Viable (reshaped):** strictly **serial** placement —
  `address set <X>` → `order submit --scheduled-time <window>` → repeat per person.
  The account default becomes a **global mutex** held across each set→submit pair; no two
  orders can be in-flight concurrently.
- **Unverified assumption this rests on:** that `order submit` **snapshots** the address at
  submit time (so a placed order keeps its address even after the default is later flipped).
  Near-certain — a placed order has a fixed address — but **not** confirmed here because
  confirming requires a real charge. Verify in Phase 2 with the first real order.

## Q2b — No way to add addresses (new blocker)

`address` exposes only `list` and `set`. There is **no `address add` / `create`**. You can
only set the default among addresses **already saved** on the payer's DoorDash account.

This directly conflicts with spec §8 ("people DM the bot their address; the bot never
scrapes it"). The CLI cannot inject a new address. **Every participant's address must be
pre-added to the payer's account via the DoorDash app/site**, once, out of band. Needs a
product decision (see Open Questions).

## Q3 — ETA in preview: YES

`search --help` names it directly: *"For per-store delivery ETA, build a cart and use
`order preview` — its `delivery_availability` block is the authoritative real-time path."*
So the timing engine reads `quote.delivery_availability` from the preview response. (Exact
sub-field not enumerated here — inspect a live preview in Phase 1.) `search` results also
carry a coarse `delivery_time` string (e.g. `"27 min"`) usable for a first-pass estimate.

## Q4 — Cart lifecycle: multiple carts, one per store

- `cart list` returns all open/unsubmitted carts (plural).
- `cart add-items` **without** `--cart-uuid` appends to the existing open cart at that store,
  or creates one if none — **one open cart per store** (confirmed in `search --help` too).
- For game night (6 people → 6 *different* stores) coexisting carts are fine. Edge case:
  two people ordering from the **same** store/chain collide on the one-cart-per-store rule.
- Because of Q2, "multiple carts" does **not** buy you multiple addresses — they all still
  resolve to the single live default.

## Q5 — Placing

- `order submit --cart-uuid <id> --yes` (also `--tip-cents`, `--scheduled-time`).
- **Charges the default payment method immediately. NOT idempotent** — a retry can double-place.
- Requires the cart to already have a delivery address (default) and a payment method.
- `order status --cart-uuid <id>` reconciles whether a submit actually went through — use it
  as the idempotency guard after any ambiguous submit.
- `order checkout-url` = browser fallback (only for edits the CLI can't express: payment
  swap, credits, mid-checkout address change). Don't offer it by default.

## Q6 — Failure mid-run: untested

Deferred to Phase 2 — deliberately fail one real placement and observe. Not knowable from help.

## Observed flakiness (confirms spec §10)

- **`cart add-items` silently drops:** first attempt returned `success: false` with **0 of 1**
  items landed (item was likely a category placeholder needing required options). Confirms the
  spec's "verify cart contents after every add, re-add what's missing, never trust exit 0."
- **`menu` returns nothing for link-out stores** (`is_link_out: true` — e.g. Little Caesars,
  Papa Johns, Pizza Hut, Cicis near this address). Filter `is_link_out` out of search results
  before trying to build a cart; those stores can't be ordered through the CLI.
- **`order reorder` is the reliable cart-builder** for testing — it produced a clean, valid,
  previewable cart on the first try where `add-items` failed.
- Some `--json-output` commands (`cart delete`, `restaurant-item-details` on some items,
  `address set`) print non-JSON or partial output on the text path — the wrapper (spec §10)
  must tolerate this, not assume every response parses.
- `cart delete` takes **only** `--cart-uuid` (no `--yes`); passing `--yes` errors.

---

## Open questions to resolve before Phase 1

1. **Address onboarding.** The CLI can't add addresses. How do participants' addresses get
   onto the payer's account? (Manual add via app once per friend? A setup checklist? This
   reshapes spec §8.)
2. **Confirm submit-time address snapshotting** (Q2's load-bearing assumption) with the first
   real Phase 2 order before building the serial placement loop on top of it.
3. **Same-store collision** (Q4): two people, one store, one-cart-per-store. Decide behavior
   (merge into one delivery? forbid? serialize as two sequential carts?).

## What this means for the build

Reshape spec §4/§9 around a **serial, default-address-mutex placement loop** driven by
**native scheduled delivery** (Q1), not a stagger engine or six held carts. Everything else
in the spec (intent resolution, memory, money gates, settlement) is unaffected.
