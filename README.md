# 🎮🍕 Game Night Order Bot

A Discord bot that orders DoorDash for your whole group, so everyone gets their own
food at their own house, all timed to show up **together**. You type in Discord, tap
a ✅ button, done.

It starts in **practice mode** (no real charges) so you can try everything for free.

---

## 💬 Commands

Type these in your Discord server.

### Just for you
| Command | What it does |
|---|---|
| `!recent` | Shows your recent DoorDash orders |
| `!usual` | Reorders your last order, shows the price, then you tap ✅ to place it |
| `!order 3` | Reorders a specific one from the `!recent` list |

### Game night (a group)
| Command | What it does |
|---|---|
| `!setup_demo 3` | Sets up 3 pretend friends to test with (uses your own saved addresses) |
| `!roster` | Shows who's in the group |
| `!gamenight 8pm` | Builds everyone's order, shows the total, then you tap ✅ **Place all**, and they're all scheduled to arrive at 8pm |

> ✅ Nothing is ever ordered until **you** tap the confirm button.

---

## 🧑‍🤝‍🧑 Ordering for real friends (example: Mary and Jane)

Say you want to feed two friends, **Mary** and **Jane**, on game night. You don't have
their addresses and you don't know what they want to eat yet. Here's the whole flow.

### You need two things from each friend

**1. Their delivery address.**
The bot can only deliver to addresses that are **saved in YOUR DoorDash account**
(it can't add new ones itself). So:
- Text Mary and Jane: *"what's your address for food delivery?"*
- Open the **DoorDash app** → **Account** → **Addresses** → **Add Address**.
- Add Mary's address, then Jane's. Now they're saved and the bot can use them.

**2. What they want to eat.**
This bot **re-orders food that's been ordered before**, like a "get the usual" button.
Mary and Jane are new, so they don't have a "usual" yet. The first time, their order
has to be placed once:
- Ask them: *"what do you want for game night?"* (say Mary wants a Chipotle bowl)
- Place that order to Mary's address one time. Now it's in your order history.
- From then on, that's **Mary's usual**, and the bot can reorder it automatically every
  game night. Same for Jane.

### After that, game night is one command

Once Mary and Jane each have an address saved and one past order, you just type:
```
!gamenight 8pm
```
The bot orders Mary's usual to Mary's house and Jane's usual to Jane's house, both timed
to arrive at 8pm. You review the total, tap ✅, and everyone eats together.

> 💡 Short version: **save each friend's address in the DoorDash app once, place their
> first order once, and after that the bot handles every game night for you.**

---

## 🛠️ Setup (about 10 minutes, one time)

**1. Get the code**
```
git clone https://github.com/goblincub/game-night-order-bot.git
cd game-night-order-bot
```

**2. Install it**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Sign in to DoorDash** (the bot orders through this)
```
dd-cli login
```

**4. Make your Discord bot.** Full click-by-click steps are in [`SETUP.md`](./SETUP.md).
You'll get two things: a **bot token** and **your Discord user ID**.

**5. Add your settings**
```
cp .env.example .env
```
Open `.env` and paste in your bot token and user ID. Leave `DRY_RUN=true` for now.

**6. Turn it on**
```
python bot.py
```
When it says `Logged in as...`, it's running! Go type `!recent` in your server. 🎉

---

## 🔒 Safety

- **Practice mode is ON by default** (`DRY_RUN=true`), so tapping ✅ only pretends. **No charges.**
- Spending caps: `MAX_PER_ORDER_CENTS` (one person) and `MAX_PER_NIGHT_CENTS` (the whole group). Over the limit means nothing gets ordered.
- **Only you** (the owner) can place orders.
- Your DoorDash login and friends' addresses never leave your computer.

### Going live (real orders)
When you're ready to order real food: open `.env`, change `DRY_RUN=true` to `DRY_RUN=false`,
and restart the bot. Start with one small order to make sure everything's right.

---

## ❓ Good to know

- **Delivers to your DoorDash default address.** The group bot switches it per person
  automatically, then sets it back. Friends' addresses must already be **saved in your
  DoorDash account** (add them in the DoorDash app first, since the bot can't add new ones).
- **Needs Python 3.9+** and [`dd-cli`](https://github.com) installed and logged in.
- Want the nerdy details? See [`docs/`](./docs/).
