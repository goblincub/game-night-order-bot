# Game Night Order Bot

A Discord bot that reorders DoorDash for a group — several people, several
addresses, all **scheduled to land together** — through `dd-cli`. Ships safe:
practice mode (`DRY_RUN`) on by default, spending caps, owner-only.

See [`SETUP.md`](./SETUP.md) to run it and [`GAME_NIGHT_BOT_SPEC.md`](./GAME_NIGHT_BOT_SPEC.md)
for the original brief.

## What it does

**Solo:**
- `!recent` — list your recent DoorDash orders
- `!usual` — reorder your latest order, preview it, confirm with a ✅ button
- `!order <n>` — reorder a specific order from `!recent`

**Group (game night):**
- `!setup_demo <n>` — build a demo roster of `n` people from your own saved addresses
- `!roster` — show who's ordering
- `!gamenight [time]` — preview everyone's order + grand total, then a **✅ Place all**
  button places them serially, each scheduled for the same arrival window

Nothing is ever charged without an explicit ✅ from the owner, and never while
`DRY_RUN=true`.

## How it works (the interesting part)

`dd-cli` delivers only to the account's **default** address, resolved live — you can't
set an address per order (proven in [`docs/dd-cli-surface.md`](./docs/dd-cli-surface.md)).
So the group engine (`group.py`) places orders **serially**: switch the default address
→ reorder → submit with `--scheduled-time` → next person → **restore the original
default**. Timing rides on DoorDash's native scheduled delivery, so everything lands
together without a stagger engine.

## Safety (spec §7)

- `DRY_RUN=true` by default — going live is a deliberate `.env` change.
- `MAX_PER_ORDER_CENTS` and `MAX_PER_NIGHT_CENTS` caps — over either = nothing placed.
- Owner-only; explicit ✅ confirmation before any placement; every placement logged to disk.
- The account default address is always restored after a group run.

## Files

| File | Role |
|---|---|
| `bot.py` | Discord commands + confirm buttons |
| `dd_cli.py` | the single `dd-cli` wrapper (money gate, dry-run, logging) |
| `group.py` | serial multi-address placement engine |
| `roster.py` | who's ordering → which saved address → their "usual" |
| `config.py` | env / `.env` loader |
| `docs/` | roadmap (`PLAN.md`) + CLI recon (`dd-cli-surface.md`) |

## Prereqs

- `dd-cli` installed and logged in — the only DoorDash surface.
- Python 3.9+ (`discord.py` 2.x runs fine on 3.9; `pip install -r requirements.txt`).

## Roadmap

Built: solo reorder + group game-night (free, reorder-based). Next: natural-language
orders ("get me tacos") via the Claude API, and SQLite order memory. See `docs/PLAN.md`.
