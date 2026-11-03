import json
import os

import aiosqlite

from .config import DB_PATH, DEFAULT_CURRENCIES, SUPERADMIN_ID
from .utils import ROLES, now_str

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL DEFAULT '',
    username TEXT,
    role TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS currencies(
    code TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fields(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    options TEXT NOT NULL DEFAULT '[]',
    required INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    needed_date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    extra TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by INTEGER,
    decided_at TEXT,
    reject_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_req_status ON requests(status);
CREATE INDEX IF NOT EXISTS ix_req_user ON requests(user_id);
CREATE INDEX IF NOT EXISTS ix_req_created ON requests(created_at);
CREATE INDEX IF NOT EXISTS ix_req_needed ON requests(needed_date);
CREATE TABLE IF NOT EXISTS history(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hist_req ON history(request_id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""


async def init(path: str = DB_PATH) -> None:
    global _db
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    from .audit import SCHEMA as AUDIT_SCHEMA
    await _db.executescript(AUDIT_SCHEMA)
    count = await fetchval("SELECT COUNT(*) FROM currencies")
    if not count:
        for i, code in enumerate(DEFAULT_CURRENCIES):
            await _db.execute("INSERT OR IGNORE INTO currencies(code, active, sort) VALUES(?,1,?)", (code, i))
    await _db.commit()


async def close() -> None:
    if _db:
        await _db.close()


async def fetchone(sql: str, *args) -> dict | None:
    async with _db.execute(sql, args) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def fetchall(sql: str, *args) -> list[dict]:
    async with _db.execute(sql, args) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def fetchval(sql: str, *args):
    async with _db.execute(sql, args) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def execute(sql: str, *args) -> aiosqlite.Cursor:
    cur = await _db.execute(sql, args)
    await _db.commit()
    return cur


# ---------------------------------------------------------------- settings
async def get_setting(key: str) -> str | None:
    return await fetchval("SELECT value FROM settings WHERE key=?", key)


async def set_setting(key: str, value: str) -> None:
    await execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", key, value)


# ---------------------------------------------------------------- users
async def upsert_user(uid: int, full_name: str, username: str | None) -> tuple[dict, bool]:
    """Foydalanuvchini qo'shadi/yangilaydi. (user, is_new) qaytaradi."""
    from . import audit  # aylanma importdan qochish uchun
    user = await get_user(uid)
    is_new = user is None
    if is_new:
        role = "superadmin" if uid == SUPERADMIN_ID else "pending"
        await execute(
            "INSERT INTO users(id, full_name, username, role, created_at) VALUES(?,?,?,?,?)",
            uid, full_name, username, role, now_str(),
        )
        await audit.write(None, "user", uid, "registered", "role", None, ROLES.get(role, role), label=full_name)
    else:
        changes = {}
        if user["full_name"] != full_name or user["username"] != username:
            changes.update(full_name=full_name, username=username)
        # Super admin faqat bitta — .env dagi ADMIN_IDS ning birinchisi
        if uid == SUPERADMIN_ID and user["role"] != "superadmin":
            changes["role"] = "superadmin"
        elif uid != SUPERADMIN_ID and user["role"] == "superadmin":
            changes["role"] = "admin"  # .env dan olib tashlangan super admin oddiy admin bo'ladi
        if changes:
            sets = ", ".join(f"{k}=?" for k in changes)
            await execute(f"UPDATE users SET {sets} WHERE id=?", *changes.values(), uid)
            if "role" in changes:
                await audit.write(None, "user", uid, "role_changed", "role", ROLES.get(user["role"], user["role"]),
                                  ROLES.get(changes["role"], changes["role"]), label=full_name)
    return await get_user(uid), is_new


async def get_user(uid: int) -> dict | None:
    return await fetchone("SELECT * FROM users WHERE id=?", uid)


async def set_role(uid: int, role: str) -> None:
    await execute("UPDATE users SET role=? WHERE id=?", role, uid)


async def list_users(offset: int = 0, limit: int = 50) -> list[dict]:
    return await fetchall(
        """SELECT u.*, (SELECT COUNT(*) FROM requests r WHERE r.user_id=u.id) AS req_count
           FROM users u ORDER BY CASE u.role WHEN 'pending' THEN 0 WHEN 'superadmin' THEN 1 WHEN 'admin' THEN 1 WHEN 'approver' THEN 2
           WHEN 'viewer' THEN 3 WHEN 'user' THEN 4 ELSE 5 END, u.full_name LIMIT ? OFFSET ?""",
        limit, offset,
    )


async def count_users() -> int:
    return await fetchval("SELECT COUNT(*) FROM users")


async def user_ids_by_roles(roles: list[str]) -> list[int]:
    marks = ",".join("?" * len(roles))
    rows = await fetchall(f"SELECT id FROM users WHERE role IN ({marks})", *roles)
    return [r["id"] for r in rows]


# ---------------------------------------------------------------- currencies
async def list_currencies(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM currencies" + (" WHERE active=1" if active_only else "") + " ORDER BY sort, code"
    return await fetchall(sql)


async def add_currency(code: str) -> None:
    sort = (await fetchval("SELECT COALESCE(MAX(sort),0)+1 FROM currencies")) or 0
    await execute("INSERT INTO currencies(code, active, sort) VALUES(?,1,?) ON CONFLICT(code) DO UPDATE SET active=1", code, sort)


async def toggle_currency(code: str) -> None:
    await execute("UPDATE currencies SET active=1-active WHERE code=?", code)


# ---------------------------------------------------------------- custom fields
def _field(row: dict | None) -> dict | None:
    if row:
        row["options"] = json.loads(row["options"] or "[]")
    return row


async def list_fields(active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM fields" + (" WHERE active=1" if active_only else "") + " ORDER BY sort, id"
    return [_field(r) for r in await fetchall(sql)]


async def get_field(fid: int) -> dict | None:
    return _field(await fetchone("SELECT * FROM fields WHERE id=?", fid))


async def add_field(name: str, ftype: str, options: list[str], required: bool) -> int:
    sort = await fetchval("SELECT COALESCE(MAX(sort),0)+1 FROM fields")
    cur = await execute(
        "INSERT INTO fields(name, type, options, required, active, sort) VALUES(?,?,?,?,1,?)",
        name, ftype, json.dumps(options, ensure_ascii=False), int(required), sort,
    )
    return cur.lastrowid


async def update_field(fid: int, **kw) -> None:
    if "options" in kw:
        kw["options"] = json.dumps(kw["options"], ensure_ascii=False)
    sets = ", ".join(f"{k}=?" for k in kw)
    await execute(f"UPDATE fields SET {sets} WHERE id=?", *kw.values(), fid)


async def delete_field(fid: int) -> None:
    await execute("DELETE FROM fields WHERE id=?", fid)


async def move_field_up(fid: int) -> None:
    fields = await list_fields()
    ids = [f["id"] for f in fields]
    if fid not in ids:
        return
    i = ids.index(fid)
    if i > 0:
        ids[i - 1], ids[i] = ids[i], ids[i - 1]
    for pos, x in enumerate(ids):
        await _db.execute("UPDATE fields SET sort=? WHERE id=?", (pos, x))
    await _db.commit()


# ---------------------------------------------------------------- requests
_REQ_SELECT = """SELECT r.*, u.full_name AS author_name, u.username AS author_username,
                        d.full_name AS decider_name
                 FROM requests r
                 LEFT JOIN users u ON u.id = r.user_id
                 LEFT JOIN users d ON d.id = r.decided_by"""


def _req(row: dict | None) -> dict | None:
    if row:
        row["extra"] = json.loads(row["extra"] or "{}")
    return row


async def create_request(user_id: int, title: str, amount: float, currency: str,
                         needed_date: str, comment: str, extra: dict) -> int:
    ts = now_str()
    cur = await execute(
        """INSERT INTO requests(user_id, title, amount, currency, needed_date, comment, extra,
                                status, created_at, updated_at) VALUES(?,?,?,?,?,?,?, 'pending', ?, ?)""",
        user_id, title, amount, currency, needed_date, comment,
        json.dumps(extra, ensure_ascii=False), ts, ts,
    )
    return cur.lastrowid


async def get_request(rid: int) -> dict | None:
    return _req(await fetchone(_REQ_SELECT + " WHERE r.id=?", rid))


async def update_request(rid: int, **kw) -> None:
    if "extra" in kw:
        kw["extra"] = json.dumps(kw["extra"], ensure_ascii=False)
    kw["updated_at"] = now_str()
    sets = ", ".join(f"{k}=?" for k in kw)
    await execute(f"UPDATE requests SET {sets} WHERE id=?", *kw.values(), rid)


async def decide(rid: int, status: str, by: int, reason: str = "") -> bool:
    """Faqat 'pending' holatdagi zayavkani o'zgartiradi (ikki tasdiqlovchi bir vaqtda bossa ham xavfsiz)."""
    ts = now_str()
    cur = await execute(
        """UPDATE requests SET status=?, decided_by=?, decided_at=?, reject_reason=?, updated_at=?
           WHERE id=? AND status='pending'""",
        status, by, ts, reason, ts, rid,
    )
    return cur.rowcount > 0


async def reopen(rid: int) -> bool:
    cur = await execute(
        """UPDATE requests SET status='pending', decided_by=NULL, decided_at=NULL, reject_reason='', updated_at=?
           WHERE id=? AND status!='pending'""",
        now_str(), rid,
    )
    return cur.rowcount > 0


def _where(user_id: int | None, status: str | None, q: str = "") -> tuple[str, list]:
    conds, args = [], []
    q = (q or "").strip()
    if q:
        if q.lstrip("#").isdigit():
            conds.append("(r.id=? OR r.title LIKE ?)")
            args += [int(q.lstrip("#")), f"%{q}%"]
        else:
            like = f"%{q}%"
            conds.append("(r.title LIKE ? OR r.comment LIKE ? OR r.user_id IN (SELECT id FROM users WHERE full_name LIKE ?))")
            args += [like, like, like]
    if user_id:
        conds.append("r.user_id=?")
        args.append(user_id)
    if status and status != "all":
        conds.append("r.status=?")
        args.append(status)
    return (" WHERE " + " AND ".join(conds)) if conds else "", args


async def list_requests(user_id: int | None, status: str | None, offset: int, limit: int, q: str = "") -> list[dict]:
    where, args = _where(user_id, status, q)
    order = " ORDER BY r.needed_date, r.id" if status == "pending" else " ORDER BY r.id DESC"
    rows = await fetchall(_REQ_SELECT + where + order + " LIMIT ? OFFSET ?", *args, limit, offset)
    return [_req(r) for r in rows]


async def count_requests(user_id: int | None, status: str | None, q: str = "") -> int:
    where, args = _where(user_id, status, q)
    return await fetchval("SELECT COUNT(*) FROM requests r" + where, *args)


async def requests_created_between(start: str | None, end: str | None) -> list[dict]:
    if start and end:
        rows = await fetchall(_REQ_SELECT + " WHERE substr(r.created_at,1,10) BETWEEN ? AND ? ORDER BY r.id", start, end)
    else:
        rows = await fetchall(_REQ_SELECT + " ORDER BY r.id")
    return [_req(r) for r in rows]


async def requests_due_between(start: str, end: str, user_id: int | None = None,
                               statuses: tuple = ("pending", "approved")) -> list[dict]:
    marks = ",".join("?" * len(statuses))
    sql = _REQ_SELECT + f" WHERE r.needed_date BETWEEN ? AND ? AND r.status IN ({marks})"
    args: list = [start, end, *statuses]
    if user_id:
        sql += " AND r.user_id=?"
        args.append(user_id)
    return [_req(r) for r in await fetchall(sql + " ORDER BY r.needed_date, r.id", *args)]


async def overdue_pending(today_iso: str, user_id: int | None = None) -> list[dict]:
    sql = _REQ_SELECT + " WHERE r.status='pending' AND r.needed_date < ?"
    args: list = [today_iso]
    if user_id:
        sql += " AND r.user_id=?"
        args.append(user_id)
    return [_req(r) for r in await fetchall(sql + " ORDER BY r.needed_date", *args)]


async def all_pending() -> list[dict]:
    return [_req(r) for r in await fetchall(_REQ_SELECT + " WHERE r.status='pending' ORDER BY r.needed_date")]


# ---------------------------------------------------------------- history
async def add_history(rid: int, user_id: int | None, action: str, details: str = "") -> None:
    await execute(
        "INSERT INTO history(request_id, user_id, action, details, created_at) VALUES(?,?,?,?,?)",
        rid, user_id, action, details, now_str(),
    )


async def get_history(rid: int) -> list[dict]:
    return await fetchall(
        """SELECT h.*, u.full_name FROM history h LEFT JOIN users u ON u.id=h.user_id
           WHERE h.request_id=? ORDER BY h.id""",
        rid,
    )
