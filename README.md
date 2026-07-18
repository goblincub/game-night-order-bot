# Game Night Order Bot

A Discord bot that turns game-night chatter into real DoorDash orders via `dd-cli`,
timed so everyone's food lands together. See [`GAME_NIGHT_BOT_SPEC.md`](./GAME_NIGHT_BOT_SPEC.md)
for the full brief.

## Status

**Phase 0 (recon) — done.** Findings are in [`docs/dd-cli-surface.md`](./docs/dd-cli-surface.md).

Headline: the CLI **cannot set a delivery address per order** — it uses the account
default, resolved live at preview/submit time (proven empirically). The "hold six
carts, one per address" design is dead; placement must be **serial** (set default →
submit → repeat), leaning on **native scheduled delivery** for timing. See the doc
for the full picture and the two open decisions before Phase 1.

## Prereqs

- `dd-cli` installed and logged in (`dd-cli login`) — it's the only DoorDash surface.
- Python **3.11+** (system Python here is 3.9 — install a newer one before Phase 1).
- `discord.py`, `anthropic` (not yet installed).

## Build order

Per spec §12. Currently entering Phase 1 (the `dd_cli.py` wrapper + money gates)
**pending** the two open decisions in the recon doc.
