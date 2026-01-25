import httpx
import time
from fastapi import HTTPException
from config import settings

BASE_URL = "https://open.er-api.com/v6/latest/RUB"

_rates_cache = None
_last_update = 0

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
            return _rates_cache
        except Exception:
            if _rates_cache:
                return _rates_cache
            raise HTTPException(status_code=503, detail="Сервис валют недоступен")

def convert_to_rub(price: float, currency: str, rates: dict) -> float:
    curr = currency.upper()
    rate = rates.get(curr, 1.0)
    return round(price / rate, 2)