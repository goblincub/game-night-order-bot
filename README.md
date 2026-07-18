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

### Set up a real friend
| Command | What it does |
|---|---|
| `!add_friend Jane iberville` | Links a friend named Jane to a saved address (matches on part of the address) |
| `!order_for Jane pizza` | Searches restaurants near Jane's place and shows a menu |
| `!add_item 3` | Adds menu item #3 to Jane's order (sizes and required choices auto-filled) |
| `!save_order` | Saves Jane's order so game night can place it |

### Game night (a group)
| Command | What it does |
|---|---|
| `!setup_demo 3` | Sets up 3 pretend friends to test with (uses your own saved addresses) |
| `!roster` | Shows who's in the group |
| `!gamenight 8pm` | Builds everyone's order, shows the total, then you tap ✅ **Place all**, and they're all scheduled to arrive at 8pm |

> ✅ Nothing is ever ordered until **you** tap the confirm button.

---

## 🧑‍🤝‍🧑 Ordering for real friends (example: Mary and Jane)

Say you want to feed two friends, **Mary** and **Jane**, on game night. Here's the whole flow.

### Step 1: Save their addresses (once)
The bot can only deliver to addresses **saved in YOUR DoorDash account** (it can't add
new ones itself). So:
- Text Mary and Jane: *"what's your address for food delivery?"*
- Open the **DoorDash app** → **Account** → **Addresses** → **Add Address**.
- Add Mary's address, then Jane's.

### Step 2: Link them and pick their food in Discord
```
!add_friend Mary main street
!order_for Mary sushi
!add_item 2
!save_order
```
`!add_friend` links Mary to her saved address (matching on part of it). `!order_for`
searches restaurants near **her** house and shows a menu. `!add_item` adds what she wants
(sizes and required choices are filled in automatically). `!save_order` locks it in.

Repeat for Jane. You can add yourself too (`!add_friend Me sun stone`).

### Step 3: Game night is one command
```
!gamenight 8pm
```
The bot builds Mary's order to Mary's house and Jane's order to Jane's house, shows you
the total, and schedules them both for 8pm. You tap ✅, and everyone eats together.

> 💡 It works even across cities (or countries): the bot searches restaurants near each
> person and checks DoorDash can actually deliver there before it lets you place anything.

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
