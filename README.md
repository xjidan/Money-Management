# 🤖 Binary Options Money Management Bot

A production-ready Telegram bot that guides traders through structured
10-trade sessions with dynamic stake sizing and risk controls.

---

## ⚡ Quick Start

### 1. Create your bot via BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **API token** you receive (looks like `123456789:ABCdef...`)

---

### 2. Install dependencies

Requires **Python 3.10+**

```bash
pip install -r requirements.txt
```

---

### 3. Set your token & run

**Linux / macOS**
```bash
export BOT_TOKEN="123456789:ABCdef..."
python bot.py
```

**Windows (PowerShell)**
```powershell
$env:BOT_TOKEN = "123456789:ABCdef..."
python bot.py
```

**Or edit `bot.py` directly** (line ~30):
```python
BOT_TOKEN = "123456789:ABCdef..."
```

---

## 🌐 Deploy to a Server (Optional)

### Option A — Screen / tmux (VPS)
```bash
# Install screen
sudo apt install screen -y

# Start a persistent session
screen -S tradebot
export BOT_TOKEN="YOUR_TOKEN"
python bot.py

# Detach: Ctrl+A then D
# Reattach: screen -r tradebot
```

### Option B — systemd service
```ini
# /etc/systemd/system/tradebot.service
[Unit]
Description=Binary Options Trade Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/tradebot
Environment="BOT_TOKEN=YOUR_TOKEN"
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now tradebot
```

---

## 🗂 Project Structure

```
tradebot/
├── bot.py           ← Main bot (all logic)
├── requirements.txt ← Dependency list
└── README.md        ← This file
```

---

## 📐 Trading Logic

| Event         | Formula                              |
|---------------|--------------------------------------|
| Base stake    | `ceil(balance × 2%)`                |
| After a WIN   | Reset → `ceil(balance × 2%)`        |
| After a LOSS  | `ceil(previous_stake × 1.6)`        |
| Win profit    | `stake × 0.85`                      |
| Hard cap      | `ceil(balance × 30%)` (auto-applied)|

### Risk Warnings Triggered When:
- Trade > 20% of balance → ⚠️ alert shown
- Trade > 30% of balance → 🔒 auto-capped
- Losing streak ≥ 4     → 🔥 streak warning
- Balance ≤ 50% initial → 🛑 drawdown warning

---

## 👥 Multi-User Support

Sessions are stored per `user_id` in an in-memory dictionary.
Each user has a fully isolated session — no cross-user interference.

> For persistent sessions across restarts, replace the `sessions` dict
> with a Redis or SQLite backend.

---

## 🔁 Session Flow

```
/start
  └─► Enter capital
        └─► Trade #1 shown (inline buttons)
              ├─► ✅ WIN  → balance up, stake resets
              └─► ❌ LOSS → balance down, stake × 1.6
                    └─► ... repeats through Trade #10
                          └─► Full summary shown
```
