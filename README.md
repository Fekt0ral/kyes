# KYES — Know Your Expenses

KYES — сервис учета подписок и расходов на них. Помогает видеть суммарные траты, контролировать категории и получать напоминания о ближайших платежах через Telegram.

**Возможности**
- CRUD подписок: название сервиса, цена, валюта, дата следующего платежа, категория, ссылка
- Отчеты: общая сумма в месяц, сводка по категориям, средняя стоимость категории
- Конвертация в предпочтительную валюту пользователя (RUB/USD/EUR) по онлайн-курсам с кэшированием
- Предупреждение о дубликатах при создании подписки (параметр `force=true`)
- Аутентификация JWT + refresh-токены, профиль пользователя и предпочтительная валюта
- Уведомления о предстоящих платежах в Telegram (Celery Beat)
- Telegram-бот для управления подписками, профилем и обращениями в поддержку

**Компоненты**
- REST API на FastAPI: `/app/main.py`
- Фоновый воркер Celery: `/app/worker.py`
- Telegram-бот: `/app/telegram_bot.py`
- База данных через SQLAlchemy (по умолчанию SQLite)

**Технологии**
FastAPI, SQLAlchemy, Pydantic Settings, Celery, Redis, python-telegram-bot, httpx, JWT (python-jose), pwdlib (argon2)

**Конфигурация (.env)**
- `SECRET_KEY` — ключ для подписи JWT
- `BOT_TOKEN` — токен Telegram-бота (обязателен для запуска приложения)
- `DATABASE_URL` — строка подключения (по умолчанию `sqlite:////Users/fekt0r/python/kyes/subscriptions.db`)
- `REDIS_URL` и `CELERY_BROKER_URL` — Redis для Celery
- `TELEGRAM_BOT_USERNAME` — используется для генерации ссылки привязки Telegram
- `TELEGRAM_SUPPORT_CHAT_ID` — чат поддержки для пересылки обращений
- `CURRENCY_API_URL`, `CACHE_TTL` — источник курсов и TTL кэша

**Быстрый старт**
1. Установить зависимости
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
2. Создать `.env` и заполнить `SECRET_KEY` и `BOT_TOKEN`
3. Запустить API
```bash
uvicorn app.main:app --reload
```
4. Запустить фоновые задачи
```bash
celery -A app.worker.celery_app worker -l info
celery -A app.worker.celery_app beat -l info
```
5. Запустить Telegram-бота
```bash
python -m app.telegram_bot
```

**API (основные маршруты)**
- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`
- `GET /auth/me`, `PATCH /auth/me`, `PATCH /auth/me/preferences`, `DELETE /auth/me`
- `POST /subscriptions`, `GET /subscriptions`, `PATCH /subscriptions/update/{sub_id}`, `DELETE /subscriptions/{sub_id}`
- `GET /subscriptions/reports/summary`, `GET /subscriptions/reports/{category}`
- `GET /subscriptions/average/{category}`

**Модель данных**
- `User` — профиль пользователя и настройки
- `Subscription` — подписка и дата следующего платежа
- `RefreshToken` — refresh-токены
- `SupportMessage` — обращения в поддержку
- `TelegramLinkToken` — токены привязки Telegram
