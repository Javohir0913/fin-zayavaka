"""Kim onlayn: foydalanuvchining oxirgi faolligi (ilova, brauzer yoki bot).

Mini App / sayt ochiq turganda har 30 soniyada qo'ng'iroqcha so'rovi keladi — shu yetarli.
Bazaga har so'rovda emas, eng ko'pi bilan WRITE_EVERY soniyada bir yoziladi.
"""
import time

from . import db

ONLINE_SECONDS = 120     # oxirgi faollik 2 daqiqa ichida bo'lsa — onlayn
WRITE_EVERY = 60
VIA = ("app", "web", "bot")

_last: dict[int, tuple[int, str]] = {}  # uid -> (bazaga yozilgan vaqt, qayerdan)
_left: dict[int, int] = {}              # uid -> ilova/saytni yopgan vaqti (real time ulanish uzildi)


async def touch(uid: int, via: str) -> None:
    now = int(time.time())
    prev = _last.get(uid)
    if prev and now - prev[0] < WRITE_EVERY and prev[1] == via:
        return
    _last[uid] = (now, via)
    await db.execute("UPDATE users SET last_seen=?, last_via=? WHERE id=?", now, via, uid)


async def mark_left(uid: int) -> None:
    """Oxirgi ochiq oyna yopildi: "hozirgina" ko'ringan, lekin endi onlayn emas."""
    now = int(time.time())
    _left[uid] = now
    prev = _last.get(uid)
    _last[uid] = (now, prev[1] if prev else "")
    await db.execute("UPDATE users SET last_seen=? WHERE id=?", now, uid)


def is_online(uid: int, last_seen: int | None, connected: set[int], now: int | None = None) -> bool:
    """Ilova/sayt ochiq (real time ulanish bor) yoki oxirgi 2 daqiqada faol bo'lgan va keyin chiqib ketmagan."""
    if uid in connected:
        return True
    if not last_seen or (now or int(time.time())) - last_seen > ONLINE_SECONDS:
        return False
    return _left.get(uid, 0) < last_seen
