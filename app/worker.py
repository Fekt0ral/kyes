from celery import Celery
from celery.schedules import crontab
from .database import SessionLocal
from .models import Subscription, User
from datetime import date, timedelta
from sqlalchemy import select
from .logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

celery_app = Celery(
    "worker",
    broker=f"redis://localhost:6379/0",
    backend=f"redis://localhost:6379/0"
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
                # Здесь позже вызовем функцию отправки в Telegram
    finally:
        db.close()