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


async def touch(uid: int, via: str) -> None:
    now = int(time.time())
    prev = _last.get(uid)
    if prev and now - prev[0] < WRITE_EVERY and prev[1] == via:
        return
    _last[uid] = (now, via)
    await db.execute("UPDATE users SET last_seen=?, last_via=? WHERE id=?", now, via, uid)


def is_online(last_seen: int | None, now: int | None = None) -> bool:
    return bool(last_seen) and (now or int(time.time())) - last_seen <= ONLINE_SECONDS
