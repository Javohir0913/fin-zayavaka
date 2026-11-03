"""Brauzer orqali kirish: Telegram Login Widget imzosi + server sessiyasi (HttpOnly cookie).

Telegram ichidagi Mini App avvalgidek initData ("tma ...") bilan ishlaydi; bu modul faqat
oddiy brauzerdan ochilgan sayt uchun.
"""
import hashlib
import hmac
import secrets
import time

from . import db
from .config import BOT_TOKEN
from .utils import now_str

COOKIE = "fz_session"
SESSION_DAYS = 30
LOGIN_MAX_AGE = 24 * 3600   # widget ma'lumoti (auth_date) shundan eski bo'lsa qabul qilinmaydi
_TOUCH_EVERY = 300          # last_seen ni har so'rovda emas, 5 daqiqada bir yangilaymiz


def verify_login(data: dict) -> dict:
    """Telegram Login Widget ma'lumotini tekshiradi (core.telegram.org/widgets/login).

    Kalit: SHA256(bot_token); imzo: HMAC-SHA256("k=v" qatorlari, alifbo tartibida, "\\n" bilan).
    Xato bo'lsa ValueError("bad_auth" | "expired").
    """
    if not isinstance(data, dict):
        raise ValueError("bad_auth")
    got = str(data.get("hash") or "")
    fields = {k: str(data[k]) for k in data if k != "hash" and data[k] is not None}
    if not got or not fields.get("id") or not fields.get("auth_date"):
        raise ValueError("bad_auth")
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        raise ValueError("bad_auth")
    try:
        age = time.time() - int(fields["auth_date"])
        int(fields["id"])
    except ValueError:
        raise ValueError("bad_auth")
    if age > LOGIN_MAX_AGE:
        raise ValueError("expired")
    return fields


def _hash(token: str) -> str:
    # Bazada tokenning o'zi emas, xeshi saqlanadi: baza nusxasi tushib qolsa ham sessiyalar o'g'irlanmaydi
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(user_id: int, user_agent: str = "") -> str:
    now = int(time.time())
    await db.execute("DELETE FROM web_sessions WHERE expires_at < ?", now)
    token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO web_sessions(token_hash, user_id, created_at, expires_at, last_seen, user_agent) VALUES(?,?,?,?,?,?)",
        _hash(token), user_id, now_str(), now + SESSION_DAYS * 86400, now, (user_agent or "")[:200],
    )
    return token


async def session_user(token: str) -> dict | None:
    if not token or len(token) > 100:
        return None
    row = await db.fetchone("SELECT * FROM web_sessions WHERE token_hash=?", _hash(token))
    now = int(time.time())
    if not row:
        return None
    if row["expires_at"] < now:
        await db.execute("DELETE FROM web_sessions WHERE token_hash=?", row["token_hash"])
        return None
    if now - row["last_seen"] > _TOUCH_EVERY:
        await db.execute("UPDATE web_sessions SET last_seen=? WHERE token_hash=?", now, row["token_hash"])
    return await db.get_user(row["user_id"])


async def delete_session(token: str) -> None:
    if token:
        await db.execute("DELETE FROM web_sessions WHERE token_hash=?", _hash(token))
