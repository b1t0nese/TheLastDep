import hashlib
import logging

from telebot import types

logger = logging.getLogger(__name__)


class Payments:
    def __init__(self, bot, api_func, secret_key: str):
        self.bot = bot
        self.api = api_func
        self.secret_key = secret_key

        @self.bot.pre_checkout_query_handler(func=lambda query: True)
        def handle_pre_checkout(pre_checkout_query):
            if self.validate_payload(pre_checkout_query.invoice_payload):
                self.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
            else:
                self.bot.answer_pre_checkout_query(
                    pre_checkout_query.id,
                    ok=False,
                    error_message="Недействительный платёж",
                )

        @self.bot.message_handler(content_types=["successful_payment"])
        def handle_success(message):
            payload = message.successful_payment.invoice_payload
            if not self.validate_payload(payload):
                logger.error(
                    "Payload verification error: payload=%s user=%s",
                    payload,
                    message.from_user.id,
                )
                self.bot.send_message(message.chat.id, "❌ Ошибка верификации платежа.")
                return

            _, price_str, user_id_str, _ = payload.split(":")
            price = int(price_str)
            user_id = int(user_id_str)
            payment_id = message.successful_payment.provider_payment_charge_id

            # Зачислить на бэкенд
            data, status = self.api(
                "post",
                f"/api/users/{user_id}/deposit",
                json={"amount": str(price)},
            )
            if status == 200:
                new_balance = data.get("balance", "?")
                self.bot.send_message(
                    message.chat.id,
                    f"✅ <b>Баланс успешно пополнен!</b>\n\n"
                    f"⭐ Зачислено: <b>{price} ⭐</b>\n"
                    f"💳 Новый баланс: <b>{new_balance} ⭐</b>\n"
                    f"🆔 ID платежа: <code>{payment_id}</code>",
                    parse_mode="HTML",
                )
                logger.info(
                    "Successful deposit: user=%s amount=%s payment_id=%s",
                    user_id, price, payment_id,
                )
            else:
                self.bot.send_message(
                    message.chat.id,
                    f"⚠️ Платёж получен, но не удалось зачислить баланс. "
                    f"Обратитесь к администратору.\n🆔 <code>{payment_id}</code>",
                    parse_mode="HTML",
                )
                logger.error(
                    "Deposit API error after payment: user=%s amount=%s err=%s",
                    user_id, price, data,
                )

    # ──────────────────────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────────────────────

    def create_deposit(self, call: types.CallbackQuery, price: int):
        """Отправляет инвойс на пополнение через Telegram Stars."""
        payload = self.generate_payload(call.from_user.id, price)
        self.bot.send_invoice(
            chat_id=call.message.chat.id,
            title=f"Пополнение баланса — {price} ⭐",
            description=(
                f"Пополнение игрового баланса на {price} звёзд.\n"
                "Звёзды будут зачислены сразу после оплаты."
            ),
            invoice_payload=payload,
            provider_token="",       # пустой для Telegram Stars (XTR)
            currency="XTR",
            prices=[types.LabeledPrice(label="Звёзды", amount=price)],
            reply_markup=self._payment_keyboard(price),
        )
        logger.info("Invoice created: user=%s amount=%s", call.from_user.id, price)

    # ──────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────

    def generate_payload(self, user_id, price) -> str:
        data = f"{user_id}:{price}:{self.secret_key}"
        h = hashlib.sha256(data.encode()).hexdigest()[:8]
        return f"deposit:{price}:{user_id}:{h}"

    def validate_payload(self, payload: str) -> bool:
        try:
            parts = payload.split(":")
            if len(parts) != 4:
                return False
            _, price, user_id, _ = parts
            return self.generate_payload(user_id, price) == payload
        except Exception:
            return False

    @staticmethod
    def _payment_keyboard(price: int) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(text=f"Оплатить {price} ⭐", pay=True))
        return kb
