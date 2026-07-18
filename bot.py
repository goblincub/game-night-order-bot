"""v1 Discord bot: reorder your own DoorDash 'usual' with a confirm button.

Commands (owner only):
  !recent          list your last few orders
  !usual           reorder your most recent order, preview, ask to confirm
  !order <number>  reorder a specific order from the !recent list

Nothing is ever charged without an explicit ✅ tap, and never while DRY_RUN=true.
Run:  caffeinate -i python bot.py
"""
from __future__ import annotations

import asyncio
import datetime
import re

import discord
from discord.ext import commands

import config
import dd_cli
import group
import menu_order
import roster

INTENTS = discord.Intents.default()
INTENTS.message_content = True  # needed to read command text

bot = commands.Bot(command_prefix="!", intents=INTENTS, help_command=None)


def _is_owner(user_id: int) -> bool:
    return config.OWNER_ID != 0 and user_id == config.OWNER_ID


def _reorderable(limit: int = 8) -> list[dd_cli.PastOrder]:
    return [o for o in dd_cli.order_history(limit=limit) if o.reorderable]


def _preview_embed(prev: dd_cli.Preview) -> discord.Embed:
    color = discord.Color.orange() if config.DRY_RUN else discord.Color.green()
    e = discord.Embed(title=f"🧾 Reorder from {prev.store_name}", color=color)
    e.add_field(name="Items", value="\n".join(f"• {i}" for i in prev.items) or "—", inline=False)
    if prev.fees:
        e.add_field(
            name="Breakdown",
            value="\n".join(f"{label}: {amt}" for label, amt in prev.fees) or "—",
            inline=False,
        )
    e.add_field(name="Total", value=f"**{prev.total_display}**", inline=False)
    if config.DRY_RUN:
        e.set_footer(text="DRY RUN — nothing will be charged. Tapping ✅ only simulates.")
    else:
        e.set_footer(text="⚠️ LIVE — tapping ✅ charges your card immediately.")
    return e


class ConfirmView(discord.ui.View):
    def __init__(self, prev: dd_cli.Preview):
        super().__init__(timeout=120)
        self.prev = prev
        self.done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Only the owner can do that.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.done:
            await asyncio.to_thread(dd_cli.cart_delete, self.prev.cart_uuid)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            result = await asyncio.to_thread(
                dd_cli.submit,
                self.prev,
                dry_run=config.DRY_RUN,
                max_per_order_cents=config.MAX_PER_ORDER_CENTS,
                tip_cents=config.TIP_CENTS,
            )
        except dd_cli.MoneyGateError as exc:
            await asyncio.to_thread(dd_cli.cart_delete, self.prev.cart_uuid)
            await interaction.followup.send(f"🛑 {exc}")
            return
        except dd_cli.DDError as exc:
            await interaction.followup.send(f"⚠️ Order failed: {exc}")
            return

        if result.get("dry_run"):
            await asyncio.to_thread(dd_cli.cart_delete, self.prev.cart_uuid)
            await interaction.followup.send(
                f"✅ **(dry run)** Would have placed {result['total_display']} at "
                f"{self.prev.store_name}. Flip `DRY_RUN=false` in .env to go live."
            )
        else:
            await interaction.followup.send(
                f"🎉 Order placed at {self.prev.store_name} for {result['total_display']}! "
                f"Track it in the DoorDash app."
            )
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await asyncio.to_thread(dd_cli.cart_delete, self.prev.cart_uuid)
        await interaction.followup.send("❌ Cancelled. Nothing placed.")
        self.stop()


async def _preview_and_ask(ctx: commands.Context, order: dd_cli.PastOrder) -> None:
    async with ctx.typing():
        try:
            cart = await asyncio.to_thread(dd_cli.reorder, order.order_uuid, order.store_id)
            prev = await asyncio.to_thread(dd_cli.preview, cart)
        except dd_cli.DDError as exc:
            await ctx.send(f"⚠️ Couldn't build that order: {exc}")
            return
    await ctx.send(embed=_preview_embed(prev), view=ConfirmView(prev))


@bot.command(name="recent")
async def recent(ctx: commands.Context):
    if not _is_owner(ctx.author.id):
        return
    orders = await asyncio.to_thread(_reorderable)
    if not orders:
        await ctx.send("No reorderable orders found.")
        return
    lines = [
        f"**{i+1}.** {o.store_name} — {', '.join(o.items[:2])}{'…' if len(o.items) > 2 else ''}"
        for i, o in enumerate(orders)
    ]
    await ctx.send("🍔 **Your recent orders** (use `!order <number>`):\n" + "\n".join(lines))


@bot.command(name="usual")
async def usual(ctx: commands.Context):
    if not _is_owner(ctx.author.id):
        return
    orders = await asyncio.to_thread(_reorderable, 1)
    if not orders:
        await ctx.send("No reorderable orders found.")
        return
    await _preview_and_ask(ctx, orders[0])


@bot.command(name="order")
async def order(ctx: commands.Context, number: int):
    if not _is_owner(ctx.author.id):
        return
    orders = await asyncio.to_thread(_reorderable)
    if not 1 <= number <= len(orders):
        await ctx.send(f"Pick a number between 1 and {len(orders)} (see `!recent`).")
        return
    await _preview_and_ask(ctx, orders[number - 1])


# --- game-night group ordering ------------------------------------------------
def _parse_arrival(text: str) -> tuple[str | None, str]:
    """'8pm' / '8:30pm' / '20:00' -> (UTC ISO string, friendly label).

    Returns (None, 'as soon as possible') if no/invalid time. Times in the past
    today roll to tomorrow.
    """
    text = (text or "").strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if not m:
        return None, "as soon as possible"
    hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and hour != 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    now = datetime.datetime.now().astimezone()
    target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    iso = target.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return iso, target.strftime("%I:%M %p").lstrip("0")


def _group_embed(results: list[group.PersonResult], grand: int, arrival_label: str) -> discord.Embed:
    color = discord.Color.orange() if config.DRY_RUN else discord.Color.green()
    e = discord.Embed(title="🎮 Game Night order", color=color)
    e.description = f"🕒 Everyone's food targets **{arrival_label}**"
    for r in results:
        if r.ok:
            where = r.address.split(",")[0] if r.address else "?"
            body = "\n".join(f"• {i}" for i in r.items[:4]) or "—"
            e.add_field(
                name=f"{r.name} — {r.store_name} · {r.total_display}",
                value=f"{body}\n📍 {where}{('  ' + r.note) if r.note else ''}",
                inline=False,
            )
        else:
            e.add_field(name=f"{r.name} — ⚠️ problem", value=r.note[:200], inline=False)
    e.add_field(name="Grand total", value=f"**${grand/100:.2f}** (payer pays; friends settle up)", inline=False)
    e.set_footer(
        text="DRY RUN — tapping ✅ only simulates, no charge."
        if config.DRY_RUN
        else "⚠️ LIVE — tapping ✅ places ALL these real orders and charges your card."
    )
    return e


class GroupConfirmView(discord.ui.View):
    def __init__(self, people, arrival_iso, arrival_label):
        super().__init__(timeout=180)
        self.people = people
        self.arrival_iso = arrival_iso
        self.arrival_label = arrival_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("Only the payer can confirm.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Place all", style=discord.ButtonStyle.success)
    async def place(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            results, grand = await asyncio.to_thread(
                group.place_all,
                self.people,
                dry_run=config.DRY_RUN,
                max_per_order_cents=config.MAX_PER_ORDER_CENTS,
                max_per_night_cents=config.MAX_PER_NIGHT_CENTS,
                scheduled_time=self.arrival_iso,
                tip_cents=config.TIP_CENTS,
            )
        except dd_cli.MoneyGateError as exc:
            await interaction.followup.send(f"🛑 {exc}")
            return
        # Settlement (spec §9)
        lines = []
        for r in results:
            if not r.ok:
                lines.append(f"⚠️ {r.name}: {r.note[:80]}")
            elif config.DRY_RUN:
                lines.append(f"• {r.name} owes **{r.total_display}** _(dry run — not placed)_")
            else:
                lines.append(f"✅ {r.name}: **{r.total_display}** placed → {r.store_name}")
        header = (
            "🧾 **(dry run)** Would have placed these — flip `DRY_RUN=false` to go live:"
            if config.DRY_RUN
            else f"🎉 Orders placed! Targeting {self.arrival_label}. Everyone owes the payer:"
        )
        await interaction.followup.send(header + "\n" + "\n".join(lines) + f"\n**Total: ${grand/100:.2f}**")
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("❌ Game night cancelled. Nothing placed.")
        self.stop()


@bot.command(name="setup_demo")
async def setup_demo(ctx: commands.Context, size: int = 3):
    if not _is_owner(ctx.author.id):
        return
    async with ctx.typing():
        try:
            people = await asyncio.to_thread(roster.build_demo_roster, size)
        except Exception as exc:  # noqa: BLE001 — surface any setup failure to the user
            await ctx.send(f"⚠️ Couldn't build a demo roster: {exc}")
            return
    lines = [f"**{p.name}** → {p.address_label.split(',')[0]} · usual: {p.store_name}" for p in people]
    await ctx.send("🎮 Demo roster ready (your own saved addresses as pretend friends):\n" + "\n".join(lines) + "\n\nNow try `!gamenight 8pm`.")


@bot.command(name="roster")
async def show_roster(ctx: commands.Context):
    if not _is_owner(ctx.author.id):
        return
    people = roster.load_roster()
    if not people:
        await ctx.send("No roster yet. Run `!setup_demo` first.")
        return
    lines = [f"**{p.name}** → {p.address_label.split(',')[0]} · usual: {p.store_name}" for p in people]
    await ctx.send("🎮 **Roster:**\n" + "\n".join(lines))


@bot.command(name="gamenight")
async def gamenight(ctx: commands.Context, *, when: str = ""):
    if not _is_owner(ctx.author.id):
        return
    people = roster.load_roster()
    if not people:
        await ctx.send("No roster yet. Run `!setup_demo` first.")
        return
    arrival_iso, arrival_label = _parse_arrival(when)
    async with ctx.typing():
        try:
            results, grand = await asyncio.to_thread(group.preview_all, people)
        except dd_cli.DDError as exc:
            await ctx.send(f"⚠️ Couldn't build the group order: {exc}")
            return
    await ctx.send(embed=_group_embed(results, grand, arrival_label), view=GroupConfirmView(people, arrival_iso, arrival_label))


# --- ordering fresh food for real friends -------------------------------------
# One in-progress "order for X" session at a time (single-owner bot).
_SESSION: dict = {}


@bot.command(name="add_friend")
async def add_friend(ctx: commands.Context, name: str, *, address_search: str = ""):
    if not _is_owner(ctx.author.id):
        return
    if not address_search:
        await ctx.send("Usage: `!add_friend <name> <part of their saved address>` "
                       "(the address must already be saved in your DoorDash app).")
        return
    addr = await asyncio.to_thread(roster.match_saved_address, address_search)
    if not addr:
        await ctx.send(f"No saved address matching “{address_search}”. Add it in the DoorDash app first.")
        return
    await asyncio.to_thread(roster.add_friend, name, addr)
    await ctx.send(f"✅ Linked **{name}** to {addr['printable']}.\nNow pick their food: `!order_for {name} <food>`")


@bot.command(name="order_for")
async def order_for(ctx: commands.Context, name: str, *, food: str = ""):
    if not _is_owner(ctx.author.id):
        return
    p = roster.get(name)
    if not p:
        await ctx.send(f"No friend named {name}. Add them first: `!add_friend {name} <address>`")
        return
    if not food:
        await ctx.send(f"Usage: `!order_for {name} <food>` (e.g. `!order_for {name} pizza`)")
        return
    async with ctx.typing():
        addr = next((a for a in await asyncio.to_thread(dd_cli.list_addresses)
                     if a["address_id"] == p.address_id), None)
        if not addr or addr.get("lat") is None:
            await ctx.send("Couldn't read that friend's address coordinates.")
            return
        stores = await asyncio.to_thread(menu_order.search_stores, food, addr["lat"], addr["lng"])
        if not stores:
            await ctx.send(f"No orderable **{food}** places found near {name}. Try another word.")
            return
        store = stores[0]
        menu_id, items = await asyncio.to_thread(menu_order.get_menu, store.store_id)
    _SESSION[ctx.author.id] = {
        "friend": p.name, "store": store, "menu_id": menu_id, "items": items,
        "entries": [], "names": [],
    }
    listing = "\n".join(f"**{i+1}.** {it.name}" for i, it in enumerate(items[:20]))
    more = f"\n_(+{len(items)-20} more)_" if len(items) > 20 else ""
    await ctx.send(
        f"🍴 **{store.name}** near {p.name} ({store.distance}, {store.eta}). Menu:\n"
        f"{listing}{more}\n\nAdd items with `!add_item <number>`, then `!save_order`."
    )


@bot.command(name="add_item")
async def add_item(ctx: commands.Context, number: int):
    if not _is_owner(ctx.author.id):
        return
    s = _SESSION.get(ctx.author.id)
    if not s:
        await ctx.send("Start with `!order_for <name> <food>` first.")
        return
    if not 1 <= number <= len(s["items"]):
        await ctx.send(f"Pick a number between 1 and {len(s['items'])}.")
        return
    item = s["items"][number - 1]
    async with ctx.typing():
        try:
            entry = await asyncio.to_thread(
                menu_order.build_item_entry, s["store"].store_id, s["menu_id"], item
            )
        except dd_cli.DDError as exc:
            await ctx.send(f"⚠️ Couldn't add {item.name}: {exc}")
            return
    s["entries"].append(entry)
    s["names"].append(item.name)
    await ctx.send(f"➕ Added **{item.name}** to {s['friend']}'s order. "
                   f"So far: {', '.join(s['names'])}.\nMore `!add_item`, or `!save_order` when done.")


@bot.command(name="save_order")
async def save_order(ctx: commands.Context):
    if not _is_owner(ctx.author.id):
        return
    s = _SESSION.get(ctx.author.id)
    if not s or not s["entries"]:
        await ctx.send("Nothing to save yet. Use `!order_for` then `!add_item`.")
        return
    await asyncio.to_thread(
        roster.set_fresh_order, s["friend"], s["store"].store_id, s["store"].name, s["menu_id"], s["entries"]
    )
    names = ", ".join(s["names"])
    del _SESSION[ctx.author.id]
    await ctx.send(f"💾 Saved **{s['friend']}**'s order ({names}) from {s['store'].name}.\n"
                   f"Add more friends, or run `!gamenight 8pm` to place everything.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | {config.summary()}")


def main() -> None:
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    if config.OWNER_ID == 0:
        raise SystemExit("OWNER_ID is missing. Put your Discord user id in .env.")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
