from datetime import datetime, timezone, timedelta
import os
import sys
import hashlib

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

if __package__ is None or __package__ == "":
    # Running as a script: add project root to sys.path
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

from config import settings
from app.database import SessionLocal, engine
from app.models import Base
from app import crud, schemas
from app.currency import get_rates, convert_price
from app.logger import get_logger, setup_logging

REG_NAME, REG_PASSWORD = range(2)
SUB_SERVICE, SUB_PRICE, SUB_CURRENCY, SUB_DATE, SUB_CATEGORY, SUB_LINK = range(2, 8)
SUPPORT_MSG = 8
PROFILE_MENU, PROFILE_EDIT_MENU, PROFILE_NAME, PROFILE_EMAIL, PROFILE_PASSWORD_CURRENT, PROFILE_PASSWORD_NEW, PROFILE_CURRENCY, PROFILE_DELETE_CONFIRM = range(9, 17)

MENU_BUTTONS = [
    ["Профиль", "Добавить подписку"],
    ["Список подписок", "Статистика"],
    ["Поддержка"],
]
MENU_KEYBOARD = ReplyKeyboardMarkup(MENU_BUTTONS, resize_keyboard=True)
PROFILE_MENU_BUTTONS = [
    ["Изменить профиль", "Удалить профиль"],
    ["Меню"],
]
PROFILE_MENU_KEYBOARD = ReplyKeyboardMarkup(PROFILE_MENU_BUTTONS, resize_keyboard=True)

def _profile_edit_keyboard(email_exists: bool):
    email_label = "Изменить email" if email_exists else "Добавить email"
    buttons = [
        ["Имя", email_label],
        ["Пароль", "Валюта"],
        ["Меню"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

CURRENCY_BUTTONS = [
    ["RUB", "USD", "EUR"],
    ["Меню"],
]
CURRENCY_KEYBOARD = ReplyKeyboardMarkup(CURRENCY_BUTTONS, resize_keyboard=True)

logger = get_logger(__name__)

def _db_session():
    return SessionLocal()

def _get_user_by_telegram(db, update: Update):
    telegram_id = str(update.effective_user.id)
    return crud.get_user_by_telegram_id(db, telegram_id)

def _link_telegram(db, user_id: int, update: Update):
    telegram_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    crud.update_user_telegram(db, user_id=user_id, telegram_id=telegram_id, telegram_chat_id=chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        token = context.args[0] if context.args else None
        if token:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            link_token = crud.get_telegram_link_token_by_hash(db, token_hash)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if not link_token or link_token.used_at is not None:
                logger.info("Попытка использовать недействительную ссылку", extra={"telegram_id": update.effective_user.id})
                await update.message.reply_text("Ссылка недействительна или уже использована.")
                return ConversationHandler.END
            if link_token.expires_at <= now:
                logger.info("Ссылка истекла", extra={"telegram_id": update.effective_user.id})
                await update.message.reply_text("Ссылка истекла. Сгенерируй новую на сайте.")
                return ConversationHandler.END
            user = crud.get_user_by_id(db, link_token.user_id)
            if not user:
                logger.info("Профиль не найден при привязке", extra={"telegram_id": update.effective_user.id})
                await update.message.reply_text("Профиль не найден.")
                return ConversationHandler.END
            existing = _get_user_by_telegram(db, update)
            if existing and existing.id != user.id:
                logger.info("Telegram уже привязан к другому пользователю", extra={"telegram_id": update.effective_user.id})
                await update.message.reply_text("Этот Telegram уже привязан к другому профилю.")
                return ConversationHandler.END
            _link_telegram(db, user.id, update)
            crud.mark_telegram_link_token_used(db, link_token, now)
            logger.info("Профиль привязан к Telegram", extra={"user_id": user.id, "telegram_id": update.effective_user.id})
            await update.message.reply_text(
                f"Профиль привязан. Привет, {user.name}!\n",
                reply_markup=MENU_KEYBOARD
            )
            return ConversationHandler.END

        user = _get_user_by_telegram(db, update)
        if user:
            _link_telegram(db, user.id, update)
            logger.info("Пользователь вошел в бота", extra={"user_id": user.id, "telegram_id": update.effective_user.id})
            await update.message.reply_text(
                f"Привет, {user.name}! Я готов.\n",
                reply_markup=MENU_KEYBOARD
            )
            return ConversationHandler.END
    finally:
        db.close()

    context.user_data["reg"] = {}
    await update.message.reply_text("Привет! Давай создадим профиль. Как тебя зовут?")
    return REG_NAME


async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    try:
        schemas.UserCreate.validate_name(name)
    except Exception:
        await update.message.reply_text("Имя должно быть 2–50 символов, только буквы/цифры/пробел/дефис. Попробуй ещё раз.")
        return REG_NAME
    context.user_data["reg"]["name"] = name
    await update.message.reply_text("Теперь пароль (8-30 символов, заглавная, строчная, цифра и спецсимвол):")
    return REG_PASSWORD


async def reg_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    try:
        schemas.UserCreate.validate_password(password)
    except Exception:
        await update.message.reply_text("Пароль не подходит. Попробуй ещё раз.")
        return REG_PASSWORD

    reg = context.user_data.get("reg", {})
    name = reg.get("name")

    db = _db_session()
    try:
        user = crud.create_user_telegram(db, name=name, password=password)
        _link_telegram(db, user.id, update)
        logger.info("Создан профиль через Telegram", extra={"user_id": user.id, "telegram_id": update.effective_user.id})
    finally:
        db.close()

    context.user_data.pop("reg", None)
    await update.message.reply_text(f"Профиль создан.", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return
        subs = crud.get_user_subscriptions(db, user_id=user.id)
        email_text = user.email if user.email else "не задан"
        await update.message.reply_text(
            f"Твой профиль:\nИмя: {user.name}\nEmail: {email_text}\nВалюта: {user.preferred_currency}\nПодписок: {len(subs)}",
            reply_markup=PROFILE_MENU_KEYBOARD
        )
    finally:
        db.close()


async def add_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
    finally:
        db.close()

    context.user_data["sub"] = {}
    await update.message.reply_text("Название сервиса?")
    return SUB_SERVICE


async def sub_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service_name = update.message.text.strip()
    try:
        schemas.SubscriptionBase._validate_service_name(service_name)
    except Exception:
        await update.message.reply_text("Название должно быть 2–100 символов. Попробуй ещё раз.")
        return SUB_SERVICE
    context.user_data["sub"]["service_name"] = service_name
    await update.message.reply_text("Цена (число):")
    return SUB_PRICE


async def sub_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("Цена должна быть числом больше 0. Попробуй ещё раз.")
        return SUB_PRICE
    context.user_data["sub"]["price"] = price
    await update.message.reply_text("Валюта (RUB / USD / EUR):")
    return SUB_CURRENCY


async def sub_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    currency = update.message.text.strip().upper()
    if currency not in {"RUB", "USD", "EUR"}:
        await update.message.reply_text("Только RUB, USD или EUR. Попробуй ещё раз.")
        return SUB_CURRENCY
    context.user_data["sub"]["currency"] = currency
    await update.message.reply_text("Дата следующего платежа (YYYY-MM-DD):")
    return SUB_DATE


async def sub_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        next_payment = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").date()
        schemas.SubscriptionBase._validate_date(next_payment)
    except Exception:
        await update.message.reply_text("Неверная дата. Формат YYYY-MM-DD и дата не в прошлом.")
        return SUB_DATE
    context.user_data["sub"]["next_payment"] = next_payment
    await update.message.reply_text("Категория (или '-' чтобы пропустить):")
    return SUB_CATEGORY


async def sub_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text.strip()
    if category == "-":
        context.user_data["sub"]["category"] = None
    else:
        try:
            schemas.SubscriptionBase._validate_category(category)
        except Exception:
            await update.message.reply_text("Категория должна быть 2–50 символов. Попробуй ещё раз.")
            return SUB_CATEGORY
        context.user_data["sub"]["category"] = category
    await update.message.reply_text("Ссылка (или '-' чтобы пропустить):")
    return SUB_LINK


async def sub_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if link == "-":
        link = None
    else:
        try:
            schemas.SubscriptionBase._validate_link(link)
        except Exception:
            await update.message.reply_text("Некорректная ссылка. Попробуй ещё раз.")
            return SUB_LINK

    sub_data = context.user_data.get("sub", {})
    sub_data["link"] = link

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
        sub_create = schemas.SubscriptionCreate(**sub_data)
        crud.create_subscription(db, subscription=sub_create, user_id=user.id)
        logger.info("Подписка добавлена через Telegram", extra={"user_id": user.id, "service_name": sub_data.get("service_name")})
    finally:
        db.close()

    context.user_data.pop("sub", None)
    await update.message.reply_text("Подписка добавлена.", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def list_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return
        subs = crud.get_user_subscriptions(db, user_id=user.id)
        if not subs:
            await update.message.reply_text("Подписок пока нет.", reply_markup=MENU_KEYBOARD)
            return
        rates = await get_rates()
        lines = []
        for sub in subs:
            display_price = convert_price(sub.price, sub.currency, user.preferred_currency, rates)
            lines.append(
                f"{sub.service_name}: {display_price} {user.preferred_currency} | след. платеж: {sub.next_payment}"
            )
        await update.message.reply_text("\n".join(lines), reply_markup=MENU_KEYBOARD)
    finally:
        db.close()


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return
        subs = crud.get_user_subscriptions(db, user_id=user.id)
        if not subs:
            await update.message.reply_text("Подписок пока нет.", reply_markup=MENU_KEYBOARD)
            return
        rates = await get_rates()
        total = 0.0
        by_category = {}
        for sub in subs:
            amount = convert_price(sub.price, sub.currency, user.preferred_currency, rates)
            total += amount
            cat = sub.category or "Без категории"
            by_category[cat] = by_category.get(cat, 0.0) + amount
        lines = [f"Итого в месяц: {round(total, 2)} {user.preferred_currency}"]
        for cat, val in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"{cat}: {round(val, 2)} {user.preferred_currency}")
        await update.message.reply_text("\n".join(lines), reply_markup=MENU_KEYBOARD)
    finally:
        db.close()


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
    finally:
        db.close()

    await update.message.reply_text("Опиши проблему одним сообщением:")
    return SUPPORT_MSG


async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        user_id = user.id if user else None
        crud.create_support_message(db, user_id=user_id, message=text)
        logger.info("Сообщение в поддержку из Telegram", extra={"user_id": user_id, "telegram_id": update.effective_user.id})
    finally:
        db.close()

    if settings.telegram_support_chat_id:
        await context.bot.send_message(
            chat_id=settings.telegram_support_chat_id,
            text=f"Запрос в поддержку от пользователя {update.effective_user.id}:\n{text}"
        )

    await update.message.reply_text("Сообщение отправлено. Спасибо!", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("reg", None)
    context.user_data.pop("sub", None)
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
    finally:
        db.close()

    await profile(update, context)
    return PROFILE_MENU

async def profile_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
        if text == "изменить профиль":
            email_exists = bool(user.email)
            await update.message.reply_text("Что изменить?", reply_markup=_profile_edit_keyboard(email_exists))
            return PROFILE_EDIT_MENU
        if text == "удалить профиль":
            await update.message.reply_text("Напиши УДАЛИТЬ для подтверждения удаления профиля.")
            return PROFILE_DELETE_CONFIRM
        if text == "меню":
            await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
            return ConversationHandler.END
        await update.message.reply_text("Выбери действие из меню.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU
    finally:
        db.close()

async def profile_edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    db = _db_session()
    if text == "имя":
        try:
            user = _get_user_by_telegram(db, update)
            if not user:
                await update.message.reply_text("Сначала нужно создать профиль: /start")
                return ConversationHandler.END
            last_name_change = _to_naive_utc(user.last_name_change)
            now = _now_naive_utc()
            if last_name_change and (now - last_name_change) < timedelta(days=1):
                await update.message.reply_text("Имя можно менять раз в сутки.", reply_markup=_profile_edit_keyboard(bool(user.email)))
                return PROFILE_EDIT_MENU
        finally:
            db.close()
        await update.message.reply_text("Новое имя:")
        return PROFILE_NAME
    if text in {"email", "изменить email", "добавить email"}:
        try:
            user = _get_user_by_telegram(db, update)
            if not user:
                await update.message.reply_text("Сначала нужно создать профиль: /start")
                return ConversationHandler.END
            last_email_change = _to_naive_utc(user.last_email_change)
            now = _now_naive_utc()
            if last_email_change and (now - last_email_change) < timedelta(days=1):
                await update.message.reply_text("Email можно менять раз в сутки.", reply_markup=_profile_edit_keyboard(bool(user.email)))
                return PROFILE_EDIT_MENU
            prompt = "Новый email:" if user.email else "Email:"
        finally:
            db.close()
        await update.message.reply_text(prompt)
        return PROFILE_EMAIL
    if text == "пароль":
        try:
            user = _get_user_by_telegram(db, update)
            if not user:
                await update.message.reply_text("Сначала нужно создать профиль: /start")
                return ConversationHandler.END
            last_password_change = _to_naive_utc(user.last_password_change)
            now = _now_naive_utc()
            if last_password_change and (now - last_password_change) < timedelta(days=1):
                await update.message.reply_text("Пароль можно менять раз в сутки.", reply_markup=_profile_edit_keyboard(bool(user.email)))
                return PROFILE_EDIT_MENU
        finally:
            db.close()
        await update.message.reply_text("Текущий пароль:")
        return PROFILE_PASSWORD_CURRENT
    if text == "валюта":
        db.close()
        await update.message.reply_text("Новая валюта:", reply_markup=CURRENCY_KEYBOARD)
        return PROFILE_CURRENCY
    if text == "меню":
        db.close()
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    db.close()
    await update.message.reply_text("Выбери пункт из меню.", reply_markup=_profile_edit_keyboard(True))
    return PROFILE_EDIT_MENU

def _to_naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def _now_naive_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

async def profile_set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "меню":
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    new_name = text
    try:
        schemas.UserCreate.validate_name(new_name)
    except Exception:
        await update.message.reply_text("Имя не подходит. Попробуй ещё раз.")
        return PROFILE_NAME

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END

        last_name_change = _to_naive_utc(user.last_name_change)
        now = _now_naive_utc()
        if last_name_change and (now - last_name_change) < timedelta(days=1):
            await update.message.reply_text("Имя можно менять раз в сутки.", reply_markup=PROFILE_MENU_KEYBOARD)
            return PROFILE_MENU

        crud.update_user_fields(db, user.id, name=new_name, last_name_change=now)
        await update.message.reply_text("Имя обновлено.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU
    finally:
        db.close()

async def profile_set_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "меню":
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    new_email = text
    try:
        schemas.UserCreate.validate_email(new_email)
    except Exception:
        await update.message.reply_text("Некорректный email. Попробуй ещё раз.")
        return PROFILE_EMAIL

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END

        if new_email == user.email:
            await update.message.reply_text("Это уже текущий email.")
            return PROFILE_MENU

        existing = crud.get_user_by_email(db, new_email)
        if existing:
            await update.message.reply_text("Email уже используется.")
            return PROFILE_EMAIL

        last_email_change = _to_naive_utc(user.last_email_change)
        now = _now_naive_utc()
        if last_email_change and (now - last_email_change) < timedelta(days=1):
            await update.message.reply_text("Email можно менять раз в сутки.", reply_markup=PROFILE_MENU_KEYBOARD)
            return PROFILE_MENU

        crud.update_user_fields(db, user.id, email=new_email, last_email_change=now)
        await update.message.reply_text("Email обновлен.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU
    finally:
        db.close()

async def profile_password_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "меню":
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    current_password = text
    context.user_data["pwd_current"] = current_password
    await update.message.reply_text("Новый пароль:")
    return PROFILE_PASSWORD_NEW

async def profile_password_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "меню":
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    new_password = text
    try:
        schemas.UserCreate.validate_password(new_password)
    except Exception:
        await update.message.reply_text("Пароль не подходит. Попробуй ещё раз.")
        return PROFILE_PASSWORD_NEW

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END

        last_password_change = _to_naive_utc(user.last_password_change)
        now = _now_naive_utc()
        if last_password_change and (now - last_password_change) < timedelta(days=1):
            await update.message.reply_text("Пароль можно менять раз в сутки.")
            return PROFILE_MENU

        current_password = context.user_data.get("pwd_current")
        if not current_password:
            await update.message.reply_text("Сначала укажи текущий пароль.")
            return PROFILE_PASSWORD_CURRENT

        from app import security  # local import to avoid circular
        if not security.verify_password(current_password, user.hashed_password):
            context.user_data.pop("pwd_current", None)
            await update.message.reply_text("Неверный текущий пароль. Введи ещё раз.")
            return PROFILE_PASSWORD_CURRENT

        hashed_password = security.get_password_hash(new_password)
        crud.update_user_fields(
            db,
            user.id,
            hashed_password=hashed_password,
            last_password_change=now,
            password_changed_at=now
        )
        crud.revoke_user_refresh_tokens(db, user.id, revoked_at=now)
        context.user_data.pop("pwd_current", None)
        await update.message.reply_text("Пароль обновлен.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU
    finally:
        db.close()

async def profile_set_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "меню":
        await update.message.reply_text("Главное меню", reply_markup=MENU_KEYBOARD)
        return ConversationHandler.END
    currency = text.upper()
    if currency not in {"RUB", "USD", "EUR"}:
        await update.message.reply_text("Выбери валюту кнопками.", reply_markup=CURRENCY_KEYBOARD)
        return PROFILE_CURRENCY

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Сначала нужно создать профиль: /start")
            return ConversationHandler.END
        crud.update_user_preferred_currency(db, user.id, currency)
        await update.message.reply_text("Валюта обновлена.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU
    finally:
        db.close()

async def profile_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text != "УДАЛИТЬ":
        await update.message.reply_text("Удаление отменено.", reply_markup=PROFILE_MENU_KEYBOARD)
        return PROFILE_MENU

    db = _db_session()
    try:
        user = _get_user_by_telegram(db, update)
        if not user:
            await update.message.reply_text("Профиль уже удален.")
            return ConversationHandler.END
        crud.delete_user(db, user.id)
    finally:
        db.close()

    await update.message.reply_text("Профиль удален. /start чтобы создать новый.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    if text in {"добавить подписку", "добавить"}:
        return await add_subscription(update, context)
    if text in {"список подписок"}:
        return await list_subscriptions(update, context)
    if text in {"статистика"}:
        return await stats(update, context)
    if text in {"поддержка"}:
        return await support(update, context)
    await update.message.reply_text("Не понял сообщение. Выбери команду из меню.", reply_markup=MENU_KEYBOARD)

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Выбери команду из меню.", reply_markup=MENU_KEYBOARD)

async def _handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Ошибка обработки апдейта", exc_info=context.error)


def build_application():
    return ApplicationBuilder().token(settings.bot_token.get_secret_value()).build()


def main():
    setup_logging()
    Base.metadata.create_all(bind=engine)
    app = build_application()

    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    sub_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_subscription)],
        states={
            SUB_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_service)],
            SUB_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_price)],
            SUB_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_currency)],
            SUB_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_date)],
            SUB_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_category)],
            SUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, sub_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    support_conv = ConversationHandler(
        entry_points=[CommandHandler("support", support)],
        states={
            SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    profile_conv = ConversationHandler(
        entry_points=[
            CommandHandler("profile", profile_menu),
            MessageHandler(filters.Regex("(?i)^профиль$"), profile_menu),
        ],
        states={
            PROFILE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_menu_choice)],
            PROFILE_EDIT_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_edit_choice)],
            PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_name)],
            PROFILE_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_email)],
            PROFILE_PASSWORD_CURRENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_password_current)],
            PROFILE_PASSWORD_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_password_new)],
            PROFILE_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_currency)],
            PROFILE_DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_delete_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(reg_conv)
    app.add_handler(sub_conv)
    app.add_handler(support_conv)
    app.add_handler(profile_conv)
    app.add_handler(CommandHandler("list", list_subscriptions))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))
    app.add_error_handler(_handle_error)

    app.run_polling()


if __name__ == "__main__":
    main()
