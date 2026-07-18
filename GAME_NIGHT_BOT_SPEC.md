# Game Night Order Bot

A Discord bot that handles food for game night: reads what people say in chat, turns it into real DoorDash orders via `dd-cli`, and times the deliveries so everyone's food lands when the session starts instead of scattered across an hour.

This document is the brief. Read it fully before writing code. Phase 0 exists because parts of this spec are inference, not fact, and Phase 0 is where you find out which parts.

---

## 1. The idea

DoorDash's own demo of `dd-cli` is an office: several coworkers, one building, one pickup order, one address. That is group ordering as it already exists everywhere.

Game night is the inverse. Six people, six cities, six separate deliveries, one shared start time. There is no cart to combine and no single address. The hard part is not "what do we get," it's "when does it land."

Discord solved *press play together* years ago. Nobody solved *eat together*.

**So the bot's real job is scheduling. Ordering is the easy part.** If you find yourself building an elaborate ordering flow and a naive timing feature, the design has inverted and you should stop.

## 2. The constraint everything hangs off

`dd-cli` runs on one MacBook against one DoorDash session. It cannot authenticate as anyone else. Therefore:

- **One payer per night.** The host, or whoever volunteered.
- **N deliveries to N addresses, billed to one account.**
- **Settlement happens afterward, out of band.** The bot tells people what they owe; it does not collect.

This is not a workaround, it matches a pattern that already exists in gaming communities. Someone buys for the group: mod team dinner, a birthday, a dev feeding the beta testers who stayed up debugging with him. Build for that case and it's a feature. Fight it and you'll end up asking six people to install a CLI to order pizza, which nobody will do.

Architecturally this means: the bot never handles anyone else's credentials, and there is exactly one card in play at all times. That is a meaningful safety property. Keep it.

## 3. Core loop

1. Session is on the calendar for 8:00pm.
2. At 7:15 the bot posts in the channel: *food?*
3. People answer however they normally talk. `thai`, `the usual`, `whatever's cheap`, `im out`, `same as tuesday`.
4. Bot resolves each into a concrete cart from that person's local stores.
5. Bot posts an itemized preview with per-person totals.
6. **Payer confirms.** Nothing is placed before this.
7. Bot computes when to place each order so they all arrive around 8:10.
8. Bot holds, re-checks ETA near placement time, places.
9. Bot posts who owes the payer what.

## 4. The timing engine

This is the actual product. Everything else is plumbing.

```
target_arrival = 20:10
for each order:
    eta        = quoted ETA from order preview, in minutes
    place_at   = target_arrival - eta - buffer
```

Alice's thai place quotes 22 minutes, so her order goes in at 19:43. Bob's pizza quotes 45, so his goes in at 19:20. Both land around 20:10.

**The wrinkle:** the ETA you get at 19:00 is not the ETA at 19:43. Restaurants get busy, drivers get scarce. A schedule computed once and trusted is a schedule that's wrong by dinner. So:

- Compute a provisional schedule from first-pass previews.
- At `place_at - 3min`, re-run preview and read the fresh ETA.
- If the fresh ETA is **longer**, place immediately, you're already late.
- If the fresh ETA is **shorter**, sleep the difference and re-check.
- Cap the correction loop. Two adjustments, then place regardless. Do not build something that can spin forever while food doesn't arrive.

**Check this before building any of it:** if `dd-cli` passes through DoorDash's native scheduled delivery, the entire engine above collapses into setting the same delivery window on every order. DoorDash supports scheduling in the app; whether the CLI exposes it is unknown. This is the single highest-value question in Phase 0.

Realistically it's a hybrid. Native scheduling windows tend to be coarse (30 minutes) and not every merchant offers them. So:

- Merchant supports scheduling → use it, target the window containing 20:10.
- Merchant doesn't → fall back to the stagger engine.

Design the scheduler with both paths from the start. Don't bolt the second one on.

## 5. Intent resolution

Two Claude API calls, not one. Keep them separate, they fail differently.

**Call A: chat → structured intent.**
Input: the raw message window plus the roster. Output: JSON only, no prose, no markdown fences.

```json
[
  {"user": "alice", "intent": "thai, nothing too spicy", "budget_cap": null, "opted_out": false},
  {"user": "bob", "intent": "USUAL", "budget_cap": 20, "opted_out": false},
  {"user": "cara", "intent": null, "budget_cap": null, "opted_out": true}
]
```

Handle: people who never answer (treat as opted out, don't guess), people who answer twice (last message wins), people who answer for someone else ("get cara the pad see ew"), jokes. The bot should be conservative. A missing order is annoying; an unwanted $30 order is a problem.

**Call B: menu + intent → cart.**
Input: one person's intent, plus the actual menu JSON from `dd-cli menu`, plus the item's option groups from `dd-cli item`. Output: item ID and option IDs.

Keep these separate because Call A is cheap and rerunnable, and Call B needs live store data that doesn't exist until you've searched. Also because when Call B picks something stupid, you want to see exactly what menu it was looking at.

## 6. Memory (this is the sticky part)

The demo recalled someone's usual Chicken Caesar without being told. In a server you sit in for months, that compounds into the actual value of the thing.

Store per-user order history in SQLite. Minimum viable:

```sql
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  discord_user TEXT NOT NULL,
  ordered_at TIMESTAMP NOT NULL,
  store_id TEXT,
  store_name TEXT,
  item_name TEXT,
  item_id TEXT,
  options_json TEXT,
  subtotal_cents INTEGER
);
```

- `"the usual"` → most frequent (store_id, item_id) pair in the last ~10 orders.
- `"same as last time"` → most recent row.
- No history and they said "the usual" → ask, don't guess.

Nobody configures anything. The bot just knows by month three. That's the feature.

## 7. Money gates

Non-negotiable. An LLM with a subprocess and a saved card is a bad combination without these. Build them in Phase 1, not Phase 5.

- `DRY_RUN=true` is the **default**. Placing requires flipping it explicitly.
- **Explicit human confirmation in Discord before any placement.** A reaction or a typed `confirm` from the payer. Not a timeout, not an implicit yes.
- `MAX_PER_PERSON_CENTS` and `MAX_PER_NIGHT_CENTS`. Exceed either → hard fail, post why, place nothing.
- Every placed order gets logged to disk with timestamp, cart UUID, total, before the confirmation returns.
- The confirmation shows the **full itemized preview including fees and tip**, not just subtotals. Fees are where the surprise lives.

If the bot ever places an order the payer did not see and approve, that's the failure mode that ends the project. Treat it that way.

## 8. Addresses and privacy

Each participant's delivery address has to live somewhere. That somewhere is a file on your laptop containing your friends' home addresses.

- Explicit opt-in. People DM the bot their address; the bot never scrapes it from anywhere.
- The address store is gitignored. Add it to `.gitignore` in the first commit, before it exists.
- Never log addresses. Not in debug output, not in error traces.
- `!forget` command that deletes a user's address and history, immediately, no confirmation flow.
- Don't put addresses in the Claude API calls. Call B needs a store menu, not a street address. Search by coordinates or zip.

You do research on this server. The people in it are your subjects in one context and your friends in another. Handle their addresses like the former even though it feels like the latter.

## 9. Architecture

```
discord bot (discord.py)
    │  listens to channel, posts previews, takes confirmation
    ▼
intent collector ──► Claude API (Call A) ──► structured intents
    │
    ▼
resolver ──► dd_cli.search / .menu / .item ──► Claude API (Call B) ──► carts
    │
    ▼
scheduler ──► computes place_at per order, holds, re-verifies ETA
    │
    ▼
dd_cli.cart_add / .preview / .place  ◄── gated on confirmation + caps
    │
    ▼
settlement ──► posts itemized per-person totals
```

**Stack:** Python 3.11+, `discord.py`, `anthropic`, `subprocess` for dd-cli, SQLite, `asyncio` for scheduling (you don't need apscheduler for this).

**Deployment:** it runs on the MacBook, because that's where the dd-cli session is. There is no hosting story and that's fine. Run it under `caffeinate -i python bot.py` so the Mac doesn't sleep at 19:40 and silently skip dinner.

## 10. The dd-cli wrapper

One module, `dd_cli.py`. Everything goes through it. No `subprocess` calls anywhere else in the codebase.

Every dd-cli command gets `--json`. Parse, never scrape stdout.

**Known flakiness** (from the public demo, so treat as directional):

- Cart adds don't all land. The demo literally shows *"Only 1 of 3 items landed, need to re-add the other two to the same cart."* So: sleep 8–10s between adds, **verify cart contents after every add**, re-add what's missing. Never assume an add worked because the command exited zero.
- Rate limiting is real. On a 403, back off 15–20s and retry. Exponential after that.
- Prefer structured `--options` over free-text special instructions. Some merchants reject special instructions entirely, and a rejected instruction can take the whole add down with it.

Wrap all of this once, in the wrapper, so the scheduler never thinks about retries.

## 11. Phase 0: recon (do this first, do not skip)

Sections 4 through 10 contain inference from a demo screenshot. Before building on them, map the real surface:

```bash
dd-cli --help
# then --help on every subcommand it lists
```

Dump everything to `docs/dd-cli-surface.md`. Then answer these, in this order:

1. **Does it support scheduled delivery?** Look for `--scheduled-for`, `--delivery-window`, or similar on the order/place command. Determines whether Section 4 is a scheduler or twenty lines.
2. **Can delivery address be set per order?** Or does it use the account default? **If it can't be overridden per order, the entire project changes shape** and you should stop and rethink before writing anything. Everything here assumes N addresses from one account.
3. **Does `order preview` return an ETA in the JSON?** The whole timing engine reads from this field. If it's not there, find where it is.
4. **What is the cart lifecycle?** Can multiple carts be open at once, or one at a time? This is an architectural fork:
   - *Multiple carts:* build all six up front, hold them, place at staggered times. Clean.
   - *One cart at a time:* you cannot hold six open carts. You must resolve intent early but **build and place each cart at its own placement time**, serially. Messier, more failure modes mid-evening, and the preview you show the payer at 19:15 is now a projection rather than a real cart.
   
   Find out before designing. It changes the scheduler completely.
5. **What does placing actually look like?** Is there a confirm step? Is it idempotent? What comes back, an order ID you can track?
6. **What happens on failure at 19:43** when nobody's watching the terminal? Test a deliberate failure before it happens for real.

## 12. Build order

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | `docs/dd-cli-surface.md` | Six questions above are answered in writing |
| 1 | `dd_cli.py` wrapper + caps + DRY_RUN | Search/menu/item/cart/preview work by hand, retries are tested |
| 2 | One real order, no Discord | A hardcoded intent puts real food at your own door |
| 3 | Discord read layer + Call A | Bot prints what it *would* order. Nothing places. |
| 4 | Timing engine, dry run | Correct placement schedule against live ETAs, placing nothing |
| 5 | Live, gated | End to end with confirmation. Test on **two** people, yourself and one volunteer. |
| 6 | Memory + settlement | `"the usual"` works; itemized totals post after |

Do not skip Phase 2. Placing one real order by hand teaches you more about the failure modes than any amount of reading the help text.

## 13. What "working" means

Not "it placed orders." Six people got food and nobody typed a restaurant name, and it all showed up inside the same ten minutes.

The honest test is subtler though, and it's the one worth instrumenting: **does this actually cut the coordination overhead, or just move it?** If the twenty minutes of "anyone eating?" becomes twenty minutes of "wait did the bot get my order," you've built a worse group chat. Log timestamps around the food conversation before and after. You have 18k messages of baseline behavior on that server and the methods to read it. Use them.

## 14. Notes for the implementer

- Don't build a web dashboard. It's a Discord bot. The interface is Discord.
- Don't abstract over multiple delivery services. There's one CLI and it's DoorDash.
- Don't add a slash-command menu system. The entire premise is that people type like people. If it needs `/order add --item`, the idea is dead.
- Resist making the bot chatty. It should post twice a night: the preview and the settlement. Maybe a third time if something breaks.
