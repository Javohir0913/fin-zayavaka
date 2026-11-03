"""Ilova ichidagi bildirishnomalar (qo'ng'iroqcha). Telegram xabarlariga qo'shimcha.

Matn bazada saqlanmaydi: faqat turi (kind) va zayavka ma'lumoti — ilova uni foydalanuvchi tilida chiqaradi.
"""
import json
from datetime import datetime, timedelta

from . import db, live
from .utils import now_str

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,             -- new_request | approved | rejected | edited | reopened | cancelled
    request_id INTEGER,
    actor_id INTEGER,
    actor_name TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',  -- {title, amount, currency, reason, details}
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_notif_user ON notifications(user_id, id);
CREATE INDEX IF NOT EXISTS ix_notif_unread ON notifications(user_id, read_at);
"""
KEEP_DAYS = 90


async def add(user_ids, kind: str, req: dict, actor: dict | None, **extra) -> None:
    data = {"title": req.get("title", ""), "amount": req.get("amount"), "currency": req.get("currency", ""), **extra}
    payload = json.dumps(data, ensure_ascii=False)
    for uid in set(user_ids):
        await db.execute(
            "INSERT INTO notifications(user_id, kind, request_id, actor_id, actor_name, data, created_at) VALUES(?,?,?,?,?,?,?)",
            uid, kind, req.get("id"), actor["id"] if actor else None, (actor or {}).get("full_name") or "", payload, now_str(),
        )
    live.notif(user_ids)


async def unread_count(uid: int) -> int:
    return await db.fetchval("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", uid) or 0


async def listing(uid: int, before: int | None = None, limit: int = 30) -> list[dict]:
    sql = "SELECT * FROM notifications WHERE user_id=?"
    args: list = [uid]
    if before:
        sql += " AND id<?"
        args.append(before)
    rows = await db.fetchall(sql + " ORDER BY id DESC LIMIT ?", *args, limit)
    for r in rows:
        try:
            r["data"] = json.loads(r["data"] or "{}")
        except ValueError:
            r["data"] = {}
    return rows


async def mark_read(uid: int, nid: int | None = None) -> None:
    if nid:
        await db.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND id=? AND read_at IS NULL", now_str(), uid, nid)
    else:
        await db.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", now_str(), uid)
    live.notif([uid])  # boshqa ochiq oynalarda ham hisoblagich yangilansin


async def purge_old(now: datetime) -> None:
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute("DELETE FROM notifications WHERE created_at < ?", cutoff)
