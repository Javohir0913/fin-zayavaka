"""Real time: server o'zgarishni darhol ochiq turgan ilova/saytlarga yuboradi (Server-Sent Events).

Hodisada ma'lumot yo'q, faqat "nima o'zgardi" belgisi bor: {"t": "req", "id": 12}.
Ilova kerakli sahifani oddiy API orqali qayta oladi, demak ruxsatlar odatdagidek tekshiriladi va
hodisa orqali hech narsa sizib chiqmaydi.

Bot va web bitta jarayonda ishlaydi, shuning uchun oddiy xotiradagi navbatlar yetarli.
"""
import asyncio
import json
import logging

from .utils import can

log = logging.getLogger(__name__)

QUEUE_MAX = 100


class Conn:
    __slots__ = ("uid", "role", "queue")

    def __init__(self, uid: int, role: str):
        self.uid, self.role = uid, role
        self.queue: asyncio.Queue = asyncio.Queue(QUEUE_MAX)


_conns: set[Conn] = set()


def connect(user: dict) -> Conn:
    c = Conn(user["id"], user["role"])
    first = not is_connected(c.uid)
    _conns.add(c)
    if first:
        presence_changed()
    return c


def disconnect(c: Conn) -> bool:
    """True — bu foydalanuvchining oxirgi ochiq oynasi edi (chaqiruvchi presence_changed() ni chaqiradi)."""
    _conns.discard(c)
    return not is_connected(c.uid)


def close_all() -> None:
    """Server to'xtayapti: barcha oqimlarni yopamiz (aks holda qayta ishga tushish kutib qoladi)."""
    for c in list(_conns):
        while not c.queue.empty():
            c.queue.get_nowait()
        c.queue.put_nowait(None)


def is_connected(uid: int) -> bool:
    return any(c.uid == uid for c in _conns)


def online_ids() -> set[int]:
    return {c.uid for c in _conns}


def _send(conns, event: dict) -> None:
    data = json.dumps(event, separators=(",", ":"))
    for c in conns:
        try:
            c.queue.put_nowait(data)
        except asyncio.QueueFull:
            # Juda sekin mijoz: navbatni tozalab "hammasini yangila" deymiz
            while not c.queue.empty():
                c.queue.get_nowait()
            c.queue.put_nowait('{"t":"all"}')


# ---------------------------------------------------------------- hodisalar
def request_changed(req: dict) -> None:
    """Zayavka yaratildi/o'zgardi: egasi va hammasini ko'ra oladiganlar."""
    if not req:
        return
    _send([c for c in _conns if c.uid == req["user_id"] or can({"role": c.role}, "view_all")],
          {"t": "req", "id": req["id"]})


def notif(user_ids) -> None:
    ids = set(user_ids)
    _send([c for c in _conns if c.uid in ids], {"t": "notif"})


def users_changed() -> None:
    _send([c for c in _conns if can({"role": c.role}, "admin")], {"t": "users"})


def presence_changed() -> None:
    users_changed()


def role_changed(uid: int, role: str) -> None:
    for c in _conns:
        if c.uid == uid:
            c.role = role
    _send([c for c in _conns if c.uid == uid], {"t": "me"})
    users_changed()


def config_changed() -> None:
    """Maydonlar, valyutalar yoki kurslar o'zgardi: hamma uchun."""
    _send(list(_conns), {"t": "config"})


def stats() -> dict:
    return {"connections": len(_conns), "users": len(online_ids())}
