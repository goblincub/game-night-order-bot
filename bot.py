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

import discord
from discord.ext import commands

import config
import dd_cli

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
