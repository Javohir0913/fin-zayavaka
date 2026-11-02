"""O'zbekiston Markaziy banki (CBU) kurslari — analitikada UZS ekvivalentini hisoblash uchun."""
import logging
import time

import aiohttp

from .config import BASE_CURRENCY, CBU_URL

log = logging.getLogger(__name__)
_CACHE_TTL = 6 * 3600
_cache: dict = {"ts": 0.0, "rates": {BASE_CURRENCY: 1.0}, "date": ""}


async def get_rates() -> tuple[dict[str, float], str]:
    """(kurslar, sana) qaytaradi. Kurs: 1 birlik valyuta = N UZS."""
    if time.time() - _cache["ts"] < _CACHE_TTL and len(_cache["rates"]) > 1:
        return _cache["rates"], _cache["date"]
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(CBU_URL) as resp:
                data = await resp.json(content_type=None)
        rates = {BASE_CURRENCY: 1.0}
        for item in data:
            nominal = float(item.get("Nominal") or 1)
            rates[item["Ccy"].upper()] = float(item["Rate"]) / nominal
        _cache.update(ts=time.time(), rates=rates, date=data[0].get("Date", "") if data else "")
    except Exception as ex:  # tarmoq yo'q bo'lsa — eski kesh bilan ishlaymiz
        log.warning("CBU kurslarini olib bo'lmadi: %s", ex)
        _cache["ts"] = time.time() - _CACHE_TTL + 300  # 5 daqiqadan keyin qayta urinish
    return _cache["rates"], _cache["date"]


def to_base(amount: float, currency: str, rates: dict[str, float]) -> float | None:
    rate = rates.get(currency.upper())
    return amount * rate if rate else None
