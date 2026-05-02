"""
Binary Options Money Management Telegram Bot
Production-ready implementation using python-telegram-bot (v20+)
"""

import math
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────
PAYOUT = 0.85
TOTAL_TRADES = 10
BASE_RISK = 0.02
LOSS_MULTIPLIER = 1.6
MAX_RISK_PCT = 0.20       # warn threshold
HARD_CAP_PCT = 0.30       # force-cap threshold
STREAK_WARN = 4
DRAWDOWN_WARN = 0.50      # 50% capital loss warning

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ─── Per-user session storage ─────────────────────────────────────────────────
# { user_id: session_dict }
sessions: dict[int, dict] = {}


# ─── Session helpers ──────────────────────────────────────────────────────────

def new_session(capital: int) -> dict:
    return {
        "initial_capital": capital,
        "balance": capital,
        "trade_number": 1,
        "wins": 0,
        "losses": 0,
        "base_risk_percent": BASE_RISK,
        "current_trade_amount": None,
        "last_result": None,
        "history": [],
        # streak tracking
        "current_streak": 0,
        "max_streak": 0,
        # extra analytics
        "max_trade_amount": 0,
        "min_balance": capital,
        # message id for in-place editing
        "message_id": None,
    }


def calculate_trade_amount(session: dict) -> int:
    balance = session["balance"]
    last_result = session["last_result"]
    last_trade = session["current_trade_amount"]

    if last_result == "loss" and last_trade is not None:
        raw = last_trade * LOSS_MULTIPLIER
    else:
        raw = balance * BASE_RISK

    amount = math.ceil(raw)

    # Hard cap: trade cannot exceed 30% of balance
    cap = math.ceil(balance * HARD_CAP_PCT)
    capped = amount > cap
    if capped:
        amount = cap

    return amount, capped


def apply_result(session: dict, result: str) -> dict:
    """Mutate session with trade result. Returns updated session."""
    trade_amount = session["current_trade_amount"]
    balance = session["balance"]

    if result == "win":
        profit = math.ceil(trade_amount * PAYOUT * 100) / 100  # keep 2dp
        balance += profit
        session["wins"] += 1
        session["current_streak"] = 0
    else:
        balance -= trade_amount
        session["losses"] += 1
        session["current_streak"] += 1
        session["max_streak"] = max(session["max_streak"], session["current_streak"])

    balance = round(balance, 2)
    session["balance"] = balance
    session["min_balance"] = min(session["min_balance"], balance)
    session["max_trade_amount"] = max(session["max_trade_amount"], trade_amount)

    session["history"].append({
        "trade_no": session["trade_number"],
        "amount": trade_amount,
        "result": result,
        "balance_after": balance,
    })

    session["last_result"] = result
    session["trade_number"] += 1
    return session


# ─── Message builders ─────────────────────────────────────────────────────────

def build_trade_message(session: dict) -> tuple[str, list, bool]:
    """
    Returns (text, inline_keyboard_rows, session_ended).
    """
    trade_no = session["trade_number"]
    balance = session["balance"]
    initial = session["initial_capital"]

    # Determine trade amount & cap flag
    trade_amount, was_capped = calculate_trade_amount(session)
    session["current_trade_amount"] = trade_amount

    win_profit = round(trade_amount * PAYOUT, 2)
    loss_impact = trade_amount

    # ── Risk alerts ──────────────────────────────────────────────────────────
    alerts = []

    if trade_amount > balance * MAX_RISK_PCT:
        alerts.append(
            "⚠️ <b>Risk Alert!</b>\n"
            "Trade size exceeds 20% of your balance.\n"
            "High risk of drawdown."
        )

    if was_capped:
        alerts.append(
            "🔒 <b>Trade Cap Applied</b>\n"
            f"Amount capped at 30% of balance → ${trade_amount}"
        )

    if session["current_streak"] >= STREAK_WARN:
        alerts.append(
            f"🔥 <b>Losing Streak Detected ({session['current_streak']}+)</b>\n"
            "Consider stopping or resetting your session."
        )

    if balance <= initial * DRAWDOWN_WARN:
        alerts.append(
            "🛑 <b>Capital Drawdown Warning!</b>\n"
            "You have lost 50% of your capital.\n"
            "It is strongly recommended to stop this session."
        )

    alert_block = ""
    if alerts:
        alert_block = "\n\n" + "\n\n".join(alerts)

    text = (
        f"📊 <b>Trade #{trade_no} / {TOTAL_TRADES}</b>\n"
        f"{'─' * 28}\n\n"
        f"💰 Balance: <b>${balance:,.2f}</b>\n"
        f"🎯 Trade Amount: <b>${trade_amount:,}</b>\n\n"
        f"📈 Win Profit: <b>+${win_profit:,.2f}</b>\n"
        f"📉 Loss Impact: <b>-${loss_impact:,}</b>\n\n"
        f"📌 Wins: <b>{session['wins']}</b> | Losses: <b>{session['losses']}</b>"
        f"{alert_block}\n\n"
        f"<i>Choose your trade result:</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅  WIN", callback_data="win"),
            InlineKeyboardButton("❌  LOSS", callback_data="loss"),
        ]
    ]

    return text, keyboard, False


def build_summary_message(session: dict) -> str:
    initial = session["initial_capital"]
    final = session["balance"]
    pl = round(final - initial, 2)
    pl_sign = "+" if pl >= 0 else ""
    status = "✅ PROFIT" if pl >= 0 else "❌ LOSS"

    drawdown_pct = round((initial - session["min_balance"]) / initial * 100, 1)

    history_lines = []
    for h in session["history"]:
        icon = "✅" if h["result"] == "win" else "❌"
        history_lines.append(
            f"  #{h['trade_no']} — ${h['amount']} → {icon} {h['result'].upper()} → ${h['balance_after']:,.2f}"
        )
    history_block = "\n".join(history_lines)

    return (
        f"📊 <b>Session Completed!</b>\n"
        f"{'─' * 28}\n\n"
        f"💰 Initial Capital: <b>${initial:,}</b>\n"
        f"💰 Final Balance: <b>${final:,.2f}</b>\n\n"
        f"📈 Total P/L: <b>{pl_sign}${pl:,.2f}</b>\n\n"
        f"✅ Wins: <b>{session['wins']}</b>\n"
        f"❌ Losses: <b>{session['losses']}</b>\n\n"
        f"🔥 Max Losing Streak: <b>{session['max_streak']}</b>\n"
        f"📌 Max Trade Used: <b>${session['max_trade_amount']:,}</b>\n"
        f"📉 Max Drawdown: <b>{drawdown_pct}%</b>\n\n"
        f"<b>Status: {status}</b>\n\n"
        f"📜 <b>Trade History:</b>\n"
        f"{history_block}\n\n"
        f"🔁 Type /start to begin a new session."
    )


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # Clear any existing session
    sessions.pop(user_id, None)
    context.user_data.clear()

    text = (
        "🚀 <b>Welcome to Smart Trade Manager</b>\n\n"
        "A structured system to manage your trades with discipline.\n\n"
        "📌 <b>Session Rules:</b>\n"
        "  • Total Trades: 10\n"
        "  • Payout: 85%\n"
        "  • Strategy: Controlled progression\n\n"
        "🎯 <b>Goal:</b>\n"
        "Minimize drawdown & recover losses efficiently.\n\n"
        "💰 <b>Enter your starting capital:</b>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_capital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Only process if no active session (trade_number == 1 and no trades yet)
    if user_id in sessions and sessions[user_id]["trade_number"] > 1:
        return  # session active; ignore stray text

    raw = update.message.text.strip().replace(",", "").replace("$", "")

    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid positive number for your capital."
        )
        return

    capital = math.ceil(value)
    session = new_session(capital)
    sessions[user_id] = session

    text, keyboard, _ = build_trade_message(session)
    msg = await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    session["message_id"] = msg.message_id


async def handle_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    result = query.data  # "win" or "loss"

    if user_id not in sessions:
        await query.edit_message_text(
            "⚠️ No active session found. Please send /start to begin."
        )
        return

    session = sessions[user_id]

    # Safety: ignore duplicate button taps on completed sessions
    if session["trade_number"] > TOTAL_TRADES:
        return

    # Apply the trade result
    apply_result(session, result)

    # Session ended?
    if session["trade_number"] > TOTAL_TRADES:
        summary = build_summary_message(session)
        await query.edit_message_text(summary, parse_mode=ParseMode.HTML)
        sessions.pop(user_id, None)
        return

    # Next trade
    text, keyboard, _ = build_trade_message(session)
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Set BOT_TOKEN environment variable before running.\n"
            "  export BOT_TOKEN='123456:ABC-...' && python bot.py"
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_capital)
    )
    app.add_handler(CallbackQueryHandler(handle_result, pattern="^(win|loss)$"))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
