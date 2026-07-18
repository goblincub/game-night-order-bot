# Setup — super simple

Do these once. Nothing here spends money (DRY_RUN is on by default).

## 1. Make a Discord bot
1. Go to https://discord.com/developers/applications → **New Application** → name it.
2. Left menu → **Bot** → **Add Bot** → **Reset Token** → **Copy** the token. Keep it secret.
3. Same page → turn ON **MESSAGE CONTENT INTENT**.
4. Left menu → **OAuth2 → URL Generator** → check **bot** → under permissions check
   **Send Messages** + **Read Message History** → copy the URL at the bottom → open it →
   add the bot to your server.

## 2. Get your own Discord user id
1. Discord → **Settings → Advanced → Developer Mode = ON**.
2. Right-click your own name → **Copy User ID**.

## 3. Fill in the settings file
In this folder:
```
cp .env.example .env
```
Open `.env` and paste in your bot token (`DISCORD_TOKEN`) and your user id (`OWNER_ID`).
Leave `DRY_RUN=true` for now.

## 4. Install and run
You need Python 3.11+ (the Mac's built-in 3.9 is too old for the newest discord library).
Easiest: `brew install python@3.12`. Then:
```
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
caffeinate -i python bot.py
```
When it says `Logged in as ...`, it's running. Leave that terminal open.

## 5. Try it (still free!)
In your Discord server, type:
```
!recent
```
then
```
!usual
```
The bot shows your last order, the price with fees, and ✅ / ❌ buttons. Tap ✅ — in dry run
it just says *"would have placed"*. **No charge.**

## 6. Going live (when you're ready — this spends money)
Edit `.env`, set `DRY_RUN=false`, restart the bot. Now tapping ✅ places a **real** order and
charges your DoorDash card. Start with one cheap order to prove it. The `MAX_PER_ORDER_CENTS`
cap still protects you from anything bigger than you set.
