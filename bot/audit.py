"""Audit log — tizimdagi har bir o'zgarish: kim, qachon, nimani, oldin -> keyin.

Yozuvlar hech qachon jismonan o'chirilmaydi: 3 oydan eskilari deleted='Y' deb belgilanadi
(super admin qayta tiklashi mumkin — deleted='N', shundan keyin avtomatik o'chirilmaydi).
"""
import json
import logging
from datetime import datetime, timedelta

from . import db
from .config import TZ
from .utils import now_str

log = logging.getLogger(__name__)

RETENTION_DAYS = 90

ENTITIES = ("request", "user", "field", "currency")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor_id INTEGER,
    actor_name TEXT NOT NULL DEFAULT '',
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '',
    entity_label TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    field TEXT NOT NULL DEFAULT '',
    old_value TEXT,
    new_value TEXT,
    deleted TEXT NOT NULL DEFAULT 'N' CHECK (deleted IN ('Y','N')),
    deleted_at TEXT,
    restored_by INTEGER,
    restored_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_deleted ON audit_log(deleted);
"""


def _txt(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return "Ha" if v else "Yo'q"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


async def write(actor: dict | None, entity: str, entity_id, action: str, field: str = "",
                old=None, new=None, label: str = "") -> None:
    """Bitta yozuv. actor=None — tizim (masalan, .env orqali rol)."""
    try:
        await db.execute(
            """INSERT INTO audit_log(created_at, actor_id, actor_name, entity, entity_id, entity_label,
                                     action, field, old_value, new_value)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            now_str(), actor["id"] if actor else None, (actor or {}).get("full_name") or ("Tizim" if not actor else ""),
            entity, str(entity_id if entity_id is not None else ""), label[:200], action, field[:100],
            _txt(old), _txt(new),
        )
    except Exception:  # log yozilmasa ham asosiy amal to'xtamasin
        log.exception("Audit log yozilmadi: %s %s %s", entity, entity_id, action)


async def write_changes(actor: dict, entity: str, entity_id, changes: list[tuple[str, object, object]],
                        label: str = "", action: str = "edited") -> None:
    """changes: [(maydon, eski, yangi), ...] — har bir maydon alohida qator."""
    for field, old, new in changes:
        await write(actor, entity, entity_id, action, field, old, new, label)


async def purge_old(now: datetime | None = None) -> int:
    """3 oydan eski yozuvlarni deleted='Y' qiladi (jismonan o'chirmaydi). Tiklanganlarga tegmaydi."""
    now = now or datetime.now(TZ)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    cur = await db.execute(
        """UPDATE audit_log SET deleted='Y', deleted_at=? WHERE deleted='N' AND restored_at IS NULL AND created_at < ?""",
        now_str(), cutoff,
    )
    if cur.rowcount:
        log.info("Audit log: %s ta eski yozuv deleted='Y' qilindi", cur.rowcount)
    return cur.rowcount


async def set_deleted(log_id: int, deleted: bool, by: dict) -> bool:
    if deleted:
        cur = await db.execute("UPDATE audit_log SET deleted='Y', deleted_at=? WHERE id=? AND deleted='N'", now_str(), log_id)
    else:
        cur = await db.execute(
            "UPDATE audit_log SET deleted='N', deleted_at=NULL, restored_by=?, restored_at=? WHERE id=? AND deleted='Y'",
            by["id"], now_str(), log_id,
        )
    return cur.rowcount > 0


def _where(entity: str | None, deleted: str, q: str, entity_id: str | None):
    conds, args = [], []
    if entity in ENTITIES:
        conds.append("entity=?")
        args.append(entity)
    if entity_id:
        conds.append("entity_id=?")
        args.append(str(entity_id))
    if deleted in ("Y", "N"):
        conds.append("deleted=?")
        args.append(deleted)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        conds.append("(actor_name LIKE ? OR entity_label LIKE ? OR field LIKE ? OR old_value LIKE ? OR new_value LIKE ? OR entity_id=?)")
        args += [like, like, like, like, like, q.lstrip("#")]
    return (" WHERE " + " AND ".join(conds)) if conds else "", args


async def query(entity: str | None = None, deleted: str = "N", q: str = "", entity_id: str | None = None,
                offset: int = 0, limit: int = 30) -> tuple[list[dict], int]:
    where, args = _where(entity, deleted, q, entity_id)
    rows = await db.fetchall(f"SELECT * FROM audit_log{where} ORDER BY id DESC LIMIT ? OFFSET ?", *args, limit, offset)
    total = await db.fetchval(f"SELECT COUNT(*) FROM audit_log{where}", *args)
    return rows, total
