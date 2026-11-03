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
from .config import BASE_CURRENCY, CBU_URL, EXCHANGERATE_API_KEY, TZ
from .utils import now_str

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


async def _from_exchangerate_api(session) -> tuple[dict, str]:
    """exchangerate-api.com (API kalit bilan, .env: EXCHANGERATE_API_KEY). Bepul tarif: 1500 so'rov/oy."""
    if not EXCHANGERATE_API_KEY:
        raise ValueError("EXCHANGERATE_API_KEY yo'q")
    data = await _fetch_json(session, f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_KEY}/latest/USD", 6)
    if data.get("result") != "success":
        raise ValueError(f"exchangerate-api: {data.get('error-type', 'error')}")
    table = {k.upper(): v for k, v in data["conversion_rates"].items()}
    day = datetime.utcfromtimestamp(data.get("time_last_update_unix", time.time())).strftime("%d.%m.%Y")
    return _from_usd_table(table), day


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


SOURCES = [
    ("CBU", _from_cbu),                              # rasmiy kurs (ba'zi xorijiy serverlardan ochilmaydi)
    ("exchangerate-api.com", _from_exchangerate_api),  # API kalit bilan — asosiy zaxira
    ("open.er-api.com", _from_er_api),
    ("jsdelivr", _from_jsdelivr),
]


def _safe(msg) -> str:
    """Xato matnidan API kalitni yashiradi (aiohttp xatolarida URL bo'lishi mumkin)."""
    s = str(msg) or type(msg).__name__
    return s.replace(EXCHANGERATE_API_KEY, "***") if EXCHANGERATE_API_KEY else s


async def refresh() -> bool:
    """Kurslarni manbalardan oladi va saqlaydi. True — muvaffaqiyatli."""
    async with aiohttp.ClientSession() as session:
        for name, fn in SOURCES:
            try:
                rates, day = await fn(session)
                if len(rates) < 3 or "USD" not in rates:
                    raise ValueError("kurslar to'liq emas")
            except Exception as ex:
                log.warning("Kurs manbasi ishlamadi (%s): %s", name, _safe(ex))
                continue
            rates[BASE_CURRENCY] = 1.0
            _cache.update(rates=rates, date=day, source=name, ts=time.time())
            await db.set_setting("rates", json.dumps({"rates": rates, "date": day, "source": name, "ts": _cache["ts"]}))
            log.info("Valyuta kurslari yangilandi: %s, %s (USD=%.2f)", name, day, rates["USD"])
            await store_today()
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


def req_base(req: dict, rates: dict[str, float]) -> float | None:
    """Zayavkaning UZS ekvivalenti — O'Z KUNINING kursi bilan (db._REQ_SELECT dagi `rate`).
    Kunlik kurs umuman yo'q bo'lsa (juda eski baza) — joriy kurs bilan."""
    rate = req.get("rate")
    if rate:
        return req["amount"] * rate
    return to_base(req["amount"], req["currency"], rates)


# ---------------------------------------------------------------- kunlik kurslar (daily_rates)
def today_str() -> str:
    return datetime.now(TZ).date().isoformat()


async def tracked_codes() -> list[str]:
    return [c["code"] for c in await db.list_currencies(active_only=False) if c["code"] != BASE_CURRENCY]


async def store_today() -> int:
    """Bugungi avto kurslarni yozadi. QO'LDA qo'yilgan (manual=1) kurslarga TEGMAYDI."""
    if len(_cache["rates"]) <= 1:
        return 0
    day, now = today_str(), now_str()
    n = 0
    for code in await tracked_codes():
        rate = _cache["rates"].get(code)
        if not rate:
            continue
        cur = await db.execute(
            """INSERT INTO daily_rates(day, code, rate, source, manual, set_at) VALUES(?,?,?,?,0,?)
               ON CONFLICT(day, code) DO UPDATE SET rate=excluded.rate, source=excluded.source, set_at=excluded.set_at
               WHERE daily_rates.manual = 0""",
            day, code, round(rate, 6), _cache["source"], now,
        )
        n += cur.rowcount
    return n


async def ensure_today() -> None:
    """Bugungi kun uchun kurs qatorlari bo'lishini ta'minlaydi (yangi kun boshlanganda, yangi valyuta qo'shilganda)."""
    if not _loaded:
        await load_saved()
    have = await db.fetchval("SELECT COUNT(*) FROM daily_rates WHERE day=?", today_str())
    if have < len(await tracked_codes()):
        await store_today()


async def day_rates(day: str) -> list[dict]:
    """Shu kun uchun har bir valyutaning kursi. Shu kun yozuvi bo'lmasa — oldingi eng yaqin kun (carried=True)."""
    if day == today_str():
        await ensure_today()
    out = []
    for c in await db.list_currencies(active_only=False):
        if c["code"] == BASE_CURRENCY:
            continue
        row = await db.fetchone(
            "SELECT * FROM daily_rates WHERE code=? AND day<=? ORDER BY day DESC LIMIT 1", c["code"], day)
        out.append({
            "code": c["code"], "active": bool(c["active"]),
            "rate": row["rate"] if row else None,
            "day": row["day"] if row else None,
            "carried": bool(row) and row["day"] != day,
            "manual": bool(row and row["manual"]),
            "source": row["source"] if row else "",
            "set_by_name": row["set_by_name"] if row else "",
            "set_at": row["set_at"] if row else None,
        })
    return out


async def history(code: str, limit: int = 60) -> list[dict]:
    return await db.fetchall(
        "SELECT * FROM daily_rates WHERE code=? ORDER BY day DESC LIMIT ?", code.upper(), limit)


def _fmt(rate) -> str:
    return "—" if rate is None else f"{rate:,.2f}".replace(",", " ")


async def set_manual(actor: dict, day: str, code: str, rate: float) -> None:
    """Qo'lda kurs: qulflanadi — API endi bu kun/valyutani yangilamaydi. Audit logga yoziladi."""
    from . import audit
    old = await db.fetchone("SELECT * FROM daily_rates WHERE day=? AND code=?", day, code)
    await db.execute(
        """INSERT INTO daily_rates(day, code, rate, source, manual, set_by, set_by_name, set_at)
           VALUES(?,?,?,'manual',1,?,?,?)
           ON CONFLICT(day, code) DO UPDATE SET rate=excluded.rate, source='manual', manual=1,
               set_by=excluded.set_by, set_by_name=excluded.set_by_name, set_at=excluded.set_at""",
        day, code, rate, actor["id"], actor.get("full_name") or "", now_str(),
    )
    old_txt = None if not old else f"{_fmt(old['rate'])} ({'qo‘lda: ' + old['set_by_name'] if old['manual'] else 'avto: ' + old['source']})"
    await audit.write(actor, "rate", f"{day} {code}", "manual", "Kurs", old_txt, f"{_fmt(rate)} (qo‘lda)", label=f"{code} · {day}")


async def set_auto(actor: dict, day: str, code: str) -> bool:
    """Qo'lda kursni bekor qilib, avtomatikka qaytaradi. Bugun uchun — darhol API kursi qo'yiladi;
    o'tgan kun uchun tarixiy API kursi yo'q, shuning uchun qiymat qoladi, faqat qulf ochiladi."""
    from . import audit
    old = await db.fetchone("SELECT * FROM daily_rates WHERE day=? AND code=?", day, code)
    if not old or not old["manual"]:
        return False
    new_rate = _cache["rates"].get(code) if day == today_str() else None
    await db.execute(
        "UPDATE daily_rates SET manual=0, source=?, rate=?, set_by=?, set_by_name=?, set_at=? WHERE day=? AND code=?",
        _cache["source"] if new_rate else "auto (qulf ochildi)", round(new_rate, 6) if new_rate else old["rate"],
        actor["id"], actor.get("full_name") or "", now_str(), day, code,
    )
    await audit.write(actor, "rate", f"{day} {code}", "auto", "Kurs",
                      f"{_fmt(old['rate'])} (qo‘lda: {old['set_by_name']})",
                      f"{_fmt(new_rate or old['rate'])} (avto)", label=f"{code} · {day}")
    return True


__all__ = ["get_rates", "to_base", "req_base", "refresh", "refresh_loop", "load_saved", "store_today",
           "ensure_today", "day_rates", "history", "set_manual", "set_auto", "TZ"]
