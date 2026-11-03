"""Valyuta kurslari — UZS ekvivalentini hisoblash uchun.

Muhim: so'rovlar hech qachon tarmoqni kutmaydi. Kurslar orqa fonda yangilanadi (refresh_loop),
bazada saqlanadi va get_rates() darhol keshdan qaytaradi.
Manbalar tartibi: CBU -> open.er-api.com -> jsdelivr (cbu.uz ba'zi xorijiy serverlardan ochilmaydi).
"""
import asyncio
import json
import logging
import time
from datetime import datetime

import aiohttp

from . import db
from .config import BASE_CURRENCY, CBU_URL, TZ

log = logging.getLogger(__name__)

REFRESH_EVERY = 6 * 3600   # muvaffaqiyatli yangilanishdan keyin
RETRY_EVERY = 15 * 60      # hamma manba ishlamasa
_cache: dict = {"rates": {BASE_CURRENCY: 1.0}, "date": "", "source": "", "ts": 0.0}
_loaded = False


async def _fetch_json(session: aiohttp.ClientSession, url: str, timeout: float):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def _from_cbu(session) -> tuple[dict, str]:
    data = await _fetch_json(session, CBU_URL, 4)
    rates = {item["Ccy"].upper(): float(item["Rate"]) / float(item.get("Nominal") or 1) for item in data}
    return rates, data[0].get("Date", "") if data else ""


def _from_usd_table(table: dict) -> dict:
    """{code: N per 1 USD} -> {code: UZS per 1 unit}."""
    uzs_per_usd = float(table["UZS"])
    return {c: uzs_per_usd / float(v) for c, v in table.items() if v}


async def _from_er_api(session) -> tuple[dict, str]:
    data = await _fetch_json(session, "https://open.er-api.com/v6/latest/USD", 6)
    if data.get("result") != "success":
        raise ValueError("er-api: result != success")
    table = {k.upper(): v for k, v in data["rates"].items()}
    day = datetime.utcfromtimestamp(data.get("time_last_update_unix", time.time())).strftime("%d.%m.%Y")
    return _from_usd_table(table), day


async def _from_jsdelivr(session) -> tuple[dict, str]:
    data = await _fetch_json(session, "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json", 6)
    table = {k.upper(): v for k, v in data["usd"].items() if len(k) == 3 and isinstance(v, (int, float))}
    day = datetime.strptime(data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    return _from_usd_table(table), day


SOURCES = [("CBU", _from_cbu), ("open.er-api.com", _from_er_api), ("jsdelivr", _from_jsdelivr)]


async def refresh() -> bool:
    """Kurslarni manbalardan oladi va saqlaydi. True — muvaffaqiyatli."""
    async with aiohttp.ClientSession() as session:
        for name, fn in SOURCES:
            try:
                rates, day = await fn(session)
                if len(rates) < 3 or "USD" not in rates:
                    raise ValueError("kurslar to'liq emas")
            except Exception as ex:
                log.warning("Kurs manbasi ishlamadi (%s): %s", name, ex or type(ex).__name__)
                continue
            rates[BASE_CURRENCY] = 1.0
            _cache.update(rates=rates, date=day, source=name, ts=time.time())
            await db.set_setting("rates", json.dumps({"rates": rates, "date": day, "source": name, "ts": _cache["ts"]}))
            log.info("Valyuta kurslari yangilandi: %s, %s (USD=%.2f)", name, day, rates["USD"])
            return True
    return False


async def load_saved() -> None:
    """Bot ishga tushganda oxirgi saqlangan kurslarni bazadan oladi (tarmoqsiz)."""
    global _loaded
    _loaded = True
    raw = await db.get_setting("rates")
    if not raw:
        return
    try:
        saved = json.loads(raw)
        _cache.update(rates=saved["rates"], date=saved.get("date", ""), source=saved.get("source", ""),
                      ts=float(saved.get("ts", 0)))
    except (ValueError, KeyError):
        log.warning("Saqlangan kurslar buzilgan, e'tiborsiz qoldirildi")


async def refresh_loop() -> None:
    await load_saved()
    while True:
        age = time.time() - _cache["ts"]
        if age >= REFRESH_EVERY or len(_cache["rates"]) <= 1:
            ok = await refresh()
            wait = REFRESH_EVERY if ok else RETRY_EVERY
        else:
            wait = REFRESH_EVERY - age
        await asyncio.sleep(max(60, wait))


async def get_rates() -> tuple[dict[str, float], str]:
    """(kurslar, sana) — DARHOL, keshdan. 1 birlik valyuta = N UZS."""
    if not _loaded:  # testlar yoki refresh_loop ishga tushmagan holat
        await load_saved()
    label = _cache["date"]
    if label and _cache["source"] and _cache["source"] != "CBU":
        label = f"{label} · {_cache['source']}"
    return _cache["rates"], label


def to_base(amount: float, currency: str, rates: dict[str, float]) -> float | None:
    rate = rates.get(currency.upper())
    return amount * rate if rate else None


__all__ = ["get_rates", "to_base", "refresh", "refresh_loop", "load_saved", "TZ"]
