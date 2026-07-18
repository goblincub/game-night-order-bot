# Official starting point — the simple version first

The full six-friends game-night bot is the destination. We are **not** building that first.
We build the smallest honest thing that works, put it on GitHub, then grow it.

## v1: "Order my usual" Discord bot (single user = you)

You type in Discord → the bot rebuilds one of **your own** past DoorDash orders, shows you
the itemized price **including fees**, and waits for you to tap **✅ Confirm** before it
places anything. Nothing is charged without that tap.

```
You:  !usual
Bot:  🧾 Reordering from Taco Bell:
        • Large Nacho Fries x1
        • Bean Burrito x1
        Subtotal $8.10 · Fees $4.32 · Total $12.42
      [ ✅ Confirm ]  [ ❌ Cancel ]        (DRY RUN — nothing will be charged)
You:  *taps ✅*
Bot:  ✅ (dry run) Would have placed order. Flip DRY_RUN=false to go live.
```

### Why this version first
- Uses **only your own** saved address — **no friends' addresses needed**.
- **Free to build and test.** Everything except the final `submit` costs $0. You spend money
  exactly once, at the end, to prove a real order goes through.
- Uses the CLI features already **proven to work** in Phase 0 (`order reorder` → `preview`
  → `submit`). No menu-parsing or AI required yet.
- It **is** Phases 1–3 of `GAME_NIGHT_BOT_SPEC.md` — nothing gets thrown away. The
  six-friends timing engine is added later on top.

### Commands (v1)
- `!recent` — list your last few orders to pick from.
- `!usual` — rebuild your most recent order, preview it, ask to confirm.
- `!order <number>` — rebuild a specific order from the `!recent` list.

### Safety (built in from commit 1 — spec §7)
- **`DRY_RUN=true` is the default.** Going live requires flipping it on purpose.
- **Explicit ✅ tap required** before any placement. No timeouts, no implicit yes.
- **`MAX_PER_ORDER_CENTS` cap.** Over it → hard stop, nothing placed.
- Only the **owner** (your Discord user id) can trigger orders.
- The confirm message shows the **full total including fees**, not just subtotal.

## What money testing looks like
| Step | Costs money? |
|---|---|
| Install, run the bot, `!recent`, `!usual`, preview, tap ✅ in DRY_RUN | **$0** |
| One real order with `DRY_RUN=false` to prove it end-to-end | ~cost of one meal, **once** |

## Roadmap after v1
1. **v1** — reorder-your-usual bot with confirm (this doc). *Free.*
2. **v2** — free-text orders ("get me tacos") via the Claude API + menu search.
3. **v3** — remember favorites in SQLite; `!usual` learns without being told.
4. **v4** — the real game-night feature: multiple people, scheduled delivery so it all lands
   together, serial placement (per `docs/dd-cli-surface.md` — the address is an account-level
   default, so orders go out one at a time). Needs friends' addresses pre-added to the account.

## Not now (resist — spec §14)
No web dashboard, no slash-command menus, no multi-service abstraction. It's a Discord bot
that talks to one CLI.
