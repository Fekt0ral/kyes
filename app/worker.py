from celery import Celery
from celery.schedules import crontab
from .database import SessionLocal
from .models import Subscription, User
from datetime import date, timedelta
from sqlalchemy import select
from .logger import get_logger, setup_logging
from config import settings
import httpx
from ..config import settings

setup_logging()
logger = get_logger(__name__)

def _send_telegram_message(chat_id: str, text: str) -> None:
    if not settings.bot_token:
        return
    token = settings.bot_token.get_secret_value()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10.0)
    except Exception:
        logger.exception("Не удалось отправить сообщение в Telegram", extra={"chat_id": chat_id})

celery_app = Celery(
    "worker",
    broker=settings.celery_broker_url,
    backend=settings.redis_url
)

celery_app.conf.beat_schedule = {
    "check-payments-every-morning": {
        "task": "app.worker.check_subscriptions_reminder",
        "schedule": crontab(hour=9, minute=0), # Запуск каждый день в 9:00
        #"schedule": 60 # test
    },
}

@celery_app.task
def check_subscriptions_reminder():
    db = SessionLocal()
    try:
        tomorrow = date.today() + timedelta(days=1)
        
        query = select(Subscription).where(Subscription.next_payment == tomorrow)
        result = db.execute(query)
        subs_to_notify = result.scalars().all()

        for sub in subs_to_notify:
            query = select(User).where(User.id == sub.user_id)
            result = db.execute(query)
            user = result.scalars().first()
            
            if user:
                logger.info(
                    "Уведомление о предстоящем платеже",
                    extra={"user_id": user.id, "sub_id": sub.id, "service_name": sub.service_name}
                )
                if user.telegram_chat_id:
                    text = (
                        f"Напоминание: завтра оплата подписки {sub.service_name}.\n"
                        f"Сумма: {sub.price} {sub.currency}\n"
                        f"Ссылка: {sub.url if sub.url else 'нет'}"
                    )
                    _send_telegram_message(user.telegram_chat_id, text)
    finally:
        db.close()
