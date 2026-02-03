import httpx
import time
from fastapi import HTTPException
from config import settings
from .logger import get_logger

BASE_URL = "https://open.er-api.com/v6/latest/RUB"

_rates_cache = None
_last_update = 0
logger = get_logger(__name__)

async def get_rates():
    global _rates_cache, _last_update
    
    current_time = time.time()
    
    if _rates_cache and (current_time - _last_update < settings.cache_ttl):
        return _rates_cache

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(BASE_URL)
            response.raise_for_status()
            data = response.json()
            
            _rates_cache = data.get("rates", {})
            _last_update = current_time
            logger.info("Курсы валют обновлены", extra={"rates_count": len(_rates_cache)})
            return _rates_cache
        except Exception:
            if _rates_cache:
                logger.warning("Ошибка обновления курсов, возвращаю кеш")
                return _rates_cache
            logger.exception("Не удалось получить курсы валют")
            raise HTTPException(status_code=503, detail="Сервис валют недоступен")

def convert_to_rub(price: float, currency: str, rates: dict) -> float:
    curr = currency.upper()
    rate = rates.get(curr, 1.0)
    return round(price / rate, 2)

def convert_price(price: float, from_currency: str, to_currency: str, rates: dict) -> float:
    from_curr = from_currency.upper()
    to_curr = to_currency.upper()
    if from_curr == to_curr:
        return round(price, 2)
    from_rate = rates.get(from_curr, 1.0)
    to_rate = rates.get(to_curr, 1.0)
    price_rub = price / from_rate
    return round(price_rub * to_rate, 2)