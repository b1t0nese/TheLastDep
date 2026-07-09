import logging
import os
import threading
import time
from decimal import Decimal

import requests
import telebot
from telebot import types
from dotenv import load_dotenv

from payment_module import Payments

load_dotenv()



def api(method: str, path: str, **kwargs):
    url = f"{BACKEND_URL}{path}"
    try:
        resp = getattr(requests, method)(url, timeout=8, **kwargs)
        return resp.json(), resp.status_code
    except Exception as e:
        logger.error("API call failed %s %s: %s", method.upper(), url, e)
        return {"error": str(e)}, 500


def ensure_user(message: types.Message):
    data, status = api(
        "post",
        "/api/users",
        json={
            "telegram_id": message.from_user.id,
            "username": message.from_user.username or message.from_user.first_name,
        },
    )
    _all_users.add(message.from_user.id)
    return data, status



logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
BACKEND_URL    = os.getenv("BACKEND_URL", "")
PAYMENT_SECRET = os.getenv("PAYMENT_SECRET", "changeme_secret123")
MIN_BET        = Decimal(os.getenv("MIN_BET", "20"))
MAX_BET        = Decimal(os.getenv("MAX_BET", "500"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
payments = Payments(bot, api, PAYMENT_SECRET)

# user_id -> {step, bet_type, value, game_id}
bet_state: dict[int, dict] = {}
# user_ids ожидающих принятия disclaimer (новые пользователи)
pending_disclaimer: set[int] = set()
# Трекинг уведомлений
_last_notified_game: int   = -1
_last_notified_start: int  = -1   # для оповещения о начале раунда
_all_users: set[int]       = set()



def _user_already_bet(user_id: int, game_id: int) -> bool:
    bets_data, status = api("get", f"/api/games/{game_id}/bets")
    if status != 200:
        return False
    return any(b["user_id"] == user_id for b in bets_data.get("bets", []))


def _do_place_bet(message: types.Message, bet_type: str, value: str, amount_str: str):
    try:
        amount = Decimal(amount_str)
    except Exception:
        bot.send_message(message.chat.id, "❌ Неверная сумма.")
        return

    game_data, status = api("get", "/api/games/current")
    game = game_data.get("game")
    if not game or game["status"] != "waiting":
        bot.send_message(message.chat.id, "❌ Ставки сейчас не принимаются.", reply_markup=main_keyboard())
        return

    if _user_already_bet(message.from_user.id, game["id"]):
        bot.send_message(
            message.chat.id,
            "⚠️ Ты уже сделал ставку в этом раунде. Одна ставка за раунд!",
            reply_markup=main_keyboard(),
        )
        return

    _do_place_bet_raw(message, bet_type, value, amount, game["id"])


def _do_place_bet_raw(message: types.Message, bet_type: str, value: str, amount: Decimal, game_id: int):
    data, status = api(
        "post",
        "/api/bets",
        json={
            "user_id": message.from_user.id,
            "game_id": game_id,
            "bet_type": bet_type,
            "value": value,
            "amount": str(amount),
        },
    )
    if status == 201:
        bot.send_message(
            message.chat.id,
            f"✅ <b>Ставка принята!</b>\n\n"
            f"🎯 Тип: <b>{bet_type}</b>\n"
            f"🔢 Значение: <b>{value}</b>\n"
            f"⭐ Сумма: <b>{amount} ⭐</b>\n\n"
            f"Баланс: <b>{data['new_balance']} ⭐</b>\n\n"
            f"Удачи! 🍀",
            reply_markup=main_keyboard(),
        )
    else:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {data.get('error', 'Неизвестная ошибка')}",
            reply_markup=main_keyboard(),
        )



def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("💰 Баланс"), types.KeyboardButton("🎲 Сделать ставку"))
    kb.row(types.KeyboardButton("⭐ Пополнить баланс"), types.KeyboardButton("📋 История"))
    kb.row(types.KeyboardButton("❓ Помощь"), types.KeyboardButton("📜 Пользовательское соглашение"))
    return kb


def pre_start_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(types.KeyboardButton("📜 Пользовательское соглашение"))
    return kb


def disclaimer_inline_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Принимаю условия", callback_data="disclaimer:accept"),
        types.InlineKeyboardButton("❌ Отказаться",       callback_data="disclaimer:decline"),
    )
    return kb


def deposit_amount_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=3)
    amounts = [10, 25, 50, 100, 250, 500]
    buttons = [
        types.InlineKeyboardButton(f"{a} ⭐", callback_data=f"dep:{a}")
        for a in amounts
    ]
    kb.add(*buttons)
    return kb


def bet_type_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔢 Номер (35✕)",       callback_data="btype:number"),
        types.InlineKeyboardButton("🔴 Красное (1✕)",      callback_data="btype:color:red"),
        types.InlineKeyboardButton("⚫ Чёрное (1✕)",       callback_data="btype:color:black"),
        types.InlineKeyboardButton("➕ Чётное (1✕)",       callback_data="btype:parity:even"),
        types.InlineKeyboardButton("➖ Нечётное (1✕)",     callback_data="btype:parity:odd"),
        types.InlineKeyboardButton("1️⃣ Дюжина 1–12 (2✕)",  callback_data="btype:dozen:1"),
        types.InlineKeyboardButton("2️⃣ Дюжина 13–24 (2✕)", callback_data="btype:dozen:2"),
        types.InlineKeyboardButton("3️⃣ Дюжина 25–36 (2✕)", callback_data="btype:dozen:3"),
        types.InlineKeyboardButton("📉 1–18 (1✕)",         callback_data="btype:half:1"),
        types.InlineKeyboardButton("📈 19–36 (1✕)",        callback_data="btype:half:2"),
    )
    return kb


def number_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=7)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"bnum:{i}") for i in range(37)]
    kb.add(*buttons)
    return kb


def cancel_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_bet"))
    return kb



DISCLAIMER_TEXT = (
    "⚠️ <b>Пользовательское соглашение</b>\n\n"
    "Прежде чем начать, внимательно прочитай условия:\n\n"
    "1. <b>Ответственность.</b> Все игры носят исключительно развлекательный характер. "
    "Автор и разработчик <b>не несут никакой ответственности</b> за любые финансовые потери, "
    "возникшие в результате участия в играх.\n\n"
    "2. <b>Средства.</b> Пополнение баланса производится через Telegram Stars. "
    "Возврат звёзд возможен только через официальные механизмы Telegram. "
    "Администрация <b>производит возврат средствn только по личному запросу и в соответствии с вашим балансом</b>.\n\n"
    "3. <b>Изменение условий.</b> Администрация вправе изменять правила игры и условия "
    "использования без предварительного уведомления.\n\n"
    "Нажимая <b>«Принимаю условия»</b>, ты соглашаешься со всем вышеперечисленным."
)


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    data, status = api("post", "/api/users", json={
            "telegram_id": message.from_user.id,
            "username": message.from_user.username or message.from_user.first_name,
    })
    _all_users.add(message.from_user.id)
    is_new = data.get("new", False)

    if is_new:
        pending_disclaimer.add(message.from_user.id)
        bot.send_message(
            message.chat.id,
            f"🎰 <b>Добро пожаловать в TheLastDep Casino!</b>\n\n"
            f"Привет, <b>{message.from_user.first_name}</b>!\n\n"
            f"Перед началом игры ознакомься с пользовательским соглашением.\n"
            f"Нажми кнопку ниже, чтобы прочитать и принять условия.",
            reply_markup=pre_start_keyboard(),
        )
    else:
        user = data.get("user", {})
        bal  = user.get("balance", "?")
        bot.send_message(
            message.chat.id,
            f"🎰 <b>С возвращением, {message.from_user.first_name}!</b>\n\n"
            f"Твой баланс: <b>{bal} ⭐</b>",
            reply_markup=main_keyboard(),
        )


@bot.message_handler(func=lambda m: m.text == "📜 Пользовательское соглашение")
def cmd_show_disclaimer(message: types.Message):
    bot.send_message(message.chat.id, DISCLAIMER_TEXT, reply_markup=disclaimer_inline_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("disclaimer:"))
def cb_disclaimer(call: types.CallbackQuery):
    action = call.data.split(":")[1]
    uid = call.from_user.id

    if action == "accept":
        pending_disclaimer.discard(uid)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(
            call.message.chat.id,
            f"🎰 <b>Добро пожаловать в TheLastDep Casino!</b>\n\n"
            f"Привет, <b>{call.from_user.first_name}</b>!\n"
            f"Тебе начислен стартовый бонус: <b>10 ⭐</b>\n\n"
            f"<b>Правила — Европейская рулетка:</b>\n"
            f"• Числа 0–36, одно зеро\n"
            f"• Ставка на номер — выигрыш 35✕\n"
            f"• Красное / Чёрное — 1✕\n"
            f"• Чётное / Нечётное — 1✕\n"
            f"• Дюжина — 2✕\n"
            f"• 1–18 / 19–36 — 1✕\n\n"
            f"Мин. ставка: <b>{MIN_BET} ⭐</b> | Макс.: <b>{MAX_BET} ⭐</b>",
            reply_markup=main_keyboard(),
        )
    else:
        pending_disclaimer.discard(uid)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(
            call.message.chat.id,
            "😔 Ты отказался от условий соглашения. Использование бота невозможно.\n"
            "Если передумаешь — нажми /start.")

    bot.answer_callback_query(call.id)


def _check_disclaimer(message: types.Message) -> bool:
    if message.from_user.id in pending_disclaimer:
        bot.send_message(message.chat.id, "⚠️ Сначала прими пользовательское соглашение выше.")
        return False
    return True



@bot.message_handler(commands=["balance"])
@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def cmd_balance(message: types.Message):
    if not _check_disclaimer(message):
        return
    ensure_user(message)
    data, status = api("get", f"/api/users/{message.from_user.id}/balance")
    if status == 200:
        bot.send_message(
            message.chat.id,
            f"⭐ Твой баланс: <b>{data['balance']} ⭐</b>",
            reply_markup=main_keyboard(),
        )
    else:
        bot.send_message(message.chat.id, "❌ Не удалось получить баланс.", reply_markup=main_keyboard())


@bot.message_handler(commands=["dep"])
@bot.message_handler(func=lambda m: m.text == "⭐ Пополнить баланс")
def cmd_deposit(message: types.Message):
    if not _check_disclaimer(message):
        return
    ensure_user(message)
    bot.send_message(
        message.chat.id,
        "⭐ <b>Пополнение баланса</b>\n\nВыбери сумму пополнения в Telegram Stars:",
        reply_markup=deposit_amount_keyboard(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def cb_deposit_amount(call: types.CallbackQuery):
    if call.from_user.id in pending_disclaimer:
        bot.answer_callback_query(call.id, "Сначала прими соглашение (/start)")
        return
    price = int(call.data.split(":")[1])
    payments.create_deposit(call, price)
    bot.answer_callback_query(call.id)


@bot.message_handler(commands=["bet"])
def cmd_bet_direct(message: types.Message):
    if not _check_disclaimer(message):
        return
    ensure_user(message)
    parts = message.text.strip().split()
    if len(parts) < 4:
        bot.send_message(
            message.chat.id,
            "📌 Использование: <code>/bet &lt;тип&gt; &lt;значение&gt; &lt;сумма&gt;</code>\n\n"
            "Примеры:\n"
            "  /bet number 7 100\n"
            "  /bet color red 50\n"
            "  /bet parity even 200\n"
            "  /bet dozen 1 150\n"
            "  /bet half 1 100",
        )
        return
    _, bet_type, value, amount_str = parts[0], parts[1], parts[2], parts[3]
    _do_place_bet(message, bet_type, value, amount_str)


@bot.message_handler(func=lambda m: m.text == "🎲 Сделать ставку")
def cmd_bet_interactive(message: types.Message):
    if not _check_disclaimer(message):
        return
    ensure_user(message)
    game_data, status = api("get", "/api/games/current")
    game = game_data.get("game")
    if not game or game["status"] != "waiting":
        bot.send_message(
            message.chat.id,
            "⏳ Сейчас ставки не принимаются. Дождитесь начала нового раунда!",
            reply_markup=main_keyboard(),
        )
        return

    if _user_already_bet(message.from_user.id, game["id"]):
        bot.send_message(
            message.chat.id,
            "⚠️ Ты уже сделал ставку в этом раунде. Одна ставка за раунд!",
            reply_markup=main_keyboard(),
        )
        return

    bot.send_message(
        message.chat.id,
        f"🎯 Раунд <b>#{game['id']}</b> — выбери тип ставки:",
        reply_markup=bet_type_keyboard(),
    )
    bet_state[message.from_user.id] = {"step": "type", "game_id": game["id"]}


@bot.callback_query_handler(func=lambda c: c.data.startswith("btype:"))
def cb_bet_type(call: types.CallbackQuery):
    if call.from_user.id in pending_disclaimer:
        bot.answer_callback_query(call.id, "Сначала прими соглашение (/start)")
        return

    user_id = call.from_user.id
    parts   = call.data.split(":")
    bet_type = parts[1]

    if len(parts) == 3:
        value = parts[2]
        state = bet_state.get(user_id, {})
        state.update({"bet_type": bet_type, "value": value, "step": "amount"})
        bet_state[user_id] = state
        bot.edit_message_text(
            f"💰 Тип: <b>{bet_type}</b>, значение: <b>{value}</b>\n\n"
            f"Введи сумму ставки ({MIN_BET}–{MAX_BET} ⭐):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=cancel_keyboard(),
        )
    elif bet_type == "number":
        state = bet_state.get(user_id, {})
        state.update({"bet_type": "number", "step": "number_pick"})
        bet_state[user_id] = state
        bot.edit_message_text("🔢 Выбери число (0–36):", call.message.chat.id,
                              call.message.message_id, reply_markup=number_keyboard())

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("bnum:"))
def cb_bet_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    number  = call.data.split(":")[1]
    state   = bet_state.get(user_id, {})
    state.update({"value": number, "step": "amount"})
    bet_state[user_id] = state

    bot.edit_message_text(
        f"💰 Ставка на номер <b>{number}</b>\n\n"
        f"Введи сумму ставки ({MIN_BET}–{MAX_BET} ⭐):",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=cancel_keyboard(),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "cancel_bet")
def cb_cancel_bet(call: types.CallbackQuery):
    bet_state.pop(call.from_user.id, None)
    bot.edit_message_text("❌ Ставка отменена.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.message_handler(
    func=lambda m: m.from_user.id in bet_state and bet_state[m.from_user.id].get("step") == "amount")
def handle_bet_amount(message: types.Message):
    user_id = message.from_user.id
    state   = bet_state.get(user_id, {})

    try:
        amount = Decimal(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Введи корректное число.")
        return

    bet_state.pop(user_id, None)

    game_id = state.get("game_id")
    if not game_id:
        gd, _ = api("get", "/api/games/current")
        g     = gd.get("game")
        if not g:
            bot.send_message(message.chat.id, "❌ Нет активного раунда.", reply_markup=main_keyboard())
            return
        game_id = g["id"]

    if _user_already_bet(user_id, game_id):
        bot.send_message(
            message.chat.id,
            "⚠️ Ты уже сделал ставку в этом раунде. Одна ставка за раунд!",
            reply_markup=main_keyboard(),
        )
        return

    _do_place_bet_raw(message, state["bet_type"], state["value"], amount, game_id)


@bot.message_handler(commands=["history"])
@bot.message_handler(func=lambda m: m.text == "📋 История")
def cmd_history(message: types.Message):
    if not _check_disclaimer(message):
        return
    ensure_user(message)
    data, status = api("get", f"/api/users/{message.from_user.id}/history")
    if status != 200:
        bot.send_message(message.chat.id, "❌ Не удалось получить историю.", reply_markup=main_keyboard())
        return

    history = data.get("history", [])[:10]
    if not history:
        bot.send_message(message.chat.id, "📭 История пустая — делай ставки!", reply_markup=main_keyboard())
        return

    lines = ["📋 <b>Последние игры:</b>\n"]
    for h in history:
        ce    = {"red": "🔴", "black": "⚫", "green": "🟢"}.get(h["result_color"], "")
        net   = Decimal(h["net"])
        ns    = f"+{net}" if net >= 0 else str(net)
        emoji = "💰" if net > 0 else ("💸" if net < 0 else "➖")
        lines.append(
            f"• Игра #{h['game_id']}: {ce} <b>{h['result_number']}</b> | "
            f"{h['bet_type']} {h['bet_value']} | "
            f"{emoji} <b>{ns} ⭐</b>"
        )

    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=main_keyboard())


@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def cmd_help(message: types.Message):
    bot.send_message(
        message.chat.id,
        "🎰 <b>TheLastDep Casino — Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Регистрация и приветствие\n"
        "/balance — Твой баланс\n"
        "/dep — Пополнить баланс через Telegram Stars\n"
        "/bet &lt;тип&gt; &lt;значение&gt; &lt;сумма&gt; — Сделать ставку\n"
        "/history — Последние 10 игр\n"
        "/help — Эта справка\n\n"
        "<b>Типы ставок:</b>\n"
        "• <code>number 0-36</code> — Ставка на число (35✕)\n"
        "• <code>color red|black</code> — Цвет (1✕)\n"
        "• <code>parity even|odd</code> — Чёт/нечет (1✕)\n"
        "• <code>dozen 1|2|3</code> — Дюжина (2✕)\n"
        "• <code>half 1|2</code> — Половина (1✕)\n\n"
        f"⭐ Ставки: от {MIN_BET} до {MAX_BET}\n"
        "🎯 Ставки принимаются только пока идёт приём (статус «ожидание»)",
        reply_markup=main_keyboard(),
    )



def _broadcast(text: str, exclude: set[int] | None = None):
    for uid in list(_all_users):
        if exclude and uid in exclude:
            continue
        try:
            bot.send_message(uid, text)
        except Exception as e:
            logger.warning("Cannot broadcast to %s: %s", uid, e)


def notifications_loop():
    global _last_notified_game, _last_notified_start
    logger.info("Notification polling thread started.")

    while True:
        try:
            time.sleep(3)
            data, status = api("get", "/api/games/current")
            if status != 200:
                continue
            current = data.get("game")

            if not current:
                continue

            game_id = current["id"]
            status_ = current["status"]

            if status_ == "waiting" and game_id != _last_notified_start:
                _last_notified_start = game_id
                _broadcast(
                    f"🎰 <b>Новый раунд #{game_id} начался!</b>\n\n"
                    f"⏳ Принимаются ставки.\n"
                    f"Сделай ставку через кнопку «🎲 Сделать ставку» или командой /bet")

            if status_ == "finished" and game_id != _last_notified_game:
                _last_notified_game = game_id
                _notify_game_result(game_id)

        except Exception as e:
            logger.error("Notification loop error: %s", e)


def _notify_game_result(game_id: int):
    result_data, status = api("get", f"/api/games/{game_id}/result")
    if status != 200:
        return

    result_num   = result_data.get("result_number")
    result_color = result_data.get("result_color", "")
    ce           = {"red": "🔴", "black": "⚫", "green": "🟢"}.get(result_color, "")
    all_bets     = result_data.get("all_bets", [])

    user_bets: dict[int, list] = {}
    for bet in all_bets:
        user_bets.setdefault(bet["user_id"], []).append(bet)

    notified_users: set[int] = set()

    for user_id, bets in user_bets.items():
        notified_users.add(user_id)
        lines = [
            f"🎰 <b>Раунд #{game_id} завершён!</b>\n",
            f"Результат: {ce} <b>{result_num}</b>\n",
        ]
        total_win = Decimal("0")
        total_bet = Decimal("0")
        for bet in bets:
            bet_amt = Decimal(bet["amount"])
            win_amt = Decimal(bet["win_amount"])
            total_bet += bet_amt
            total_win += win_amt
            if win_amt > 0:
                lines.append(f"✅ {bet['bet_type']} {bet['value']}: <b>+{win_amt} ⭐</b>")
            else:
                lines.append(f"❌ {bet['bet_type']} {bet['value']}: <b>-{bet_amt} ⭐</b>")

        net    = total_win - total_bet
        net_str = f"+{net}" if net >= 0 else str(net)
        lines.append(f"\n💰 Итог: <b>{net_str} ⭐</b>")

        bal_data, _ = api("get", f"/api/users/{user_id}/balance")
        if "balance" in bal_data:
            lines.append(f"💳 Баланс: <b>{bal_data['balance']} ⭐</b>")

        try:
            bot.send_message(user_id, "\n".join(lines))
        except Exception as e:
            logger.warning("Cannot notify user %s: %s", user_id, e)

    _broadcast(f"🎰 <b>Раунд #{game_id} завершён!</b>\n"
               f"Результат: {ce} <b>{result_num}</b>", exclude=notified_users)



if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        exit(1)
    notify_thread = threading.Thread(target=notifications_loop, daemon=True)
    notify_thread.start()
    logger.info("Bot started...")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)