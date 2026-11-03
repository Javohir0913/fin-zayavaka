"""Telegram Mini App uchun HTTP API + statik fayllar (bot bilan bitta jarayonda ishlaydi)."""
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from . import audit, db, inbox, presence, reports, services, webauth
from . import rates as rates_mod
from .config import BASE_CURRENCY, BOT_TOKEN, WEB_HOST, WEB_PORT

from .rates import get_rates, req_base
from .render import fmt_field_value
from .utils import (FIELD_TYPES, PERMS, allowed_roles, can, e, fmt_amount, fmt_date,
                    role_change_error, today)

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "webapp"
INIT_DATA_MAX_AGE = 24 * 3600
PAGE = 20

BOT_KEY = web.AppKey("bot", Bot)
BOT_NAME_KEY = web.AppKey("bot_username", str)


# ---------------------------------------------------------------- yordamchilar
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


def ok(data=None, status: int = 200) -> web.Response:
    return web.json_response(data if data is not None else {"ok": True}, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))


async def body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ApiError(400, "bad_json")
    if not isinstance(data, dict):
        raise ApiError(400, "bad_json")
    return data


def need(user: dict, perm: str) -> None:
    if not can(user, perm):
        raise ApiError(403, "forbidden")


def req_id(request: web.Request) -> int:
    try:
        return int(request.match_info["rid"])
    except (KeyError, ValueError):
        raise ApiError(404, "not_found")


def public_extra(extra: dict, fields_by_id: dict) -> dict:
    out = {}
    for k, v in extra.items():
        f = fields_by_id.get(k)
        if f and f["type"] == "file" and isinstance(v, dict):
            out[k] = {"kind": v.get("kind"), "name": v.get("name")}
        else:
            out[k] = v
    return out


def can_edit(user: dict, r: dict) -> bool:
    return can(user, "admin") or (r["user_id"] == user["id"] and r["status"] == "pending")


def serialize(r: dict, user: dict, fields_by_id: dict, rates: dict | None = None) -> dict:
    is_author = r["user_id"] == user["id"]
    out = {
        "id": r["id"], "title": r["title"], "amount": r["amount"], "currency": r["currency"],
        "needed_date": r["needed_date"], "comment": r["comment"], "status": r["status"],
        "user_id": r["user_id"], "author_name": r.get("author_name"), "author_username": r.get("author_username"),
        "decider_name": r.get("decider_name"), "decided_at": r["decided_at"], "reject_reason": r["reject_reason"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
        "extra": public_extra(r["extra"], fields_by_id),
        # Zayavka kiritilgan kun kursi (qo'lda bo'lsa — kim qo'ygani)
        "rate": r.get("rate"), "rate_day": r.get("rate_used_day"), "rate_manual": bool(r.get("rate_manual")),
        "rate_source": r.get("rate_source"), "rate_set_by": r.get("rate_set_by"), "rate_set_at": r.get("rate_set_at"),
        "can": {
            "edit": can_edit(user, r),
            "decide": r["status"] == "pending" and can(user, "decide"),
            "cancel": is_author and r["status"] == "pending",
            "reopen": can(user, "admin") and r["status"] != "pending",
        },
    }
    if rates is not None:
        v = req_base(r, rates)
        out["base_amount"] = round(v, 2) if v is not None else None
    return out


async def fields_map() -> tuple[list[dict], dict]:
    fields = await db.list_fields()
    return fields, {str(f["id"]): f for f in fields}


def validate_value(f: dict, v):
    """Qo'shimcha maydon qiymatini tekshiradi. None = bo'sh."""
    t = f["type"]
    if v is None or v == "":
        return None
    if t == "text":
        v = str(v).strip()
        if len(v) > 1000:
            raise ApiError(400, "too_long", f["name"])
        return v or None
    if t == "number":
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise ApiError(400, "bad_number", f["name"])
        if n != n or abs(n) > 1e15:
            raise ApiError(400, "bad_number", f["name"])
        return round(n, 4)
    if t == "date":
        try:
            return date.fromisoformat(str(v)[:10]).isoformat()
        except ValueError:
            raise ApiError(400, "bad_date", f["name"])
    if t == "choice":
        if v not in f["options"]:
            raise ApiError(400, "bad_choice", f["name"])
        return v
    if t == "bool":
        return bool(v)
    if t == "file":
        if not (isinstance(v, dict) and isinstance(v.get("file_id"), str) and v.get("kind") in ("photo", "document")):
            raise ApiError(400, "bad_file", f["name"])
        return {"kind": v["kind"], "file_id": v["file_id"][:300], "name": str(v.get("name") or "file")[:120]}
    return None


def validate_core(data: dict, partial: bool, currencies: set[str]) -> dict:
    out = {}
    if "title" in data or not partial:
        title = str(data.get("title") or "").strip()
        if not 3 <= len(title) <= 500:
            raise ApiError(400, "bad_title")
        out["title"] = title
    if "amount" in data or not partial:
        try:
            amount = round(float(data.get("amount")), 2)
        except (TypeError, ValueError):
            raise ApiError(400, "bad_amount")
        if not 0 < amount < 1e15:
            raise ApiError(400, "bad_amount")
        out["amount"] = amount
    if "currency" in data or not partial:
        cur = str(data.get("currency") or "").upper()
        if cur not in currencies:
            raise ApiError(400, "bad_currency")
        out["currency"] = cur
    if "needed_date" in data or not partial:
        try:
            d = date.fromisoformat(str(data.get("needed_date"))[:10])
        except ValueError:
            raise ApiError(400, "bad_date")
        if not partial and d < today():
            raise ApiError(400, "past_date")
        out["needed_date"] = d.isoformat()
    if "comment" in data or not partial:
        c = str(data.get("comment") or "").strip()
        if len(c) > 1000:
            raise ApiError(400, "too_long")
        out["comment"] = c
    return out


# ---------------------------------------------------------------- autentifikatsiya
@web.middleware
async def auth_mw(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        resp = await handler(request)
        if request.path.startswith("/static/") and request.query.get("v"):
            # index.html fayl versiyasini (mtime) URL ga qo'shadi — o'zgarsa URL ham o'zgaradi,
            # shuning uchun brauzer qayta tekshirmasdan keshdan oladi (okean orqali so'rov tejaladi)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache"
        return resp
    try:
        if request.path in PUBLIC_API:
            return await handler(request)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("tma "):
            # Telegram ichidagi Mini App: initData imzosi
            try:
                init = safe_parse_webapp_init_data(BOT_TOKEN, auth[4:])
            except ValueError:
                raise ApiError(401, "bad_auth")
            if time.time() - init.auth_date.timestamp() > INIT_DATA_MAX_AGE:
                raise ApiError(401, "expired")
            tg = init.user
            if not tg:
                raise ApiError(401, "bad_auth")
            full_name = " ".join(x for x in (tg.first_name, tg.last_name) if x) or str(tg.id)
            user, is_new = await db.upsert_user(tg.id, full_name, tg.username)
            if is_new and user["role"] == "pending":
                await services.notify_new_user(request.app[BOT_KEY], tg.id, full_name, tg.username)
            lang = tg.language_code or "uz"
        else:
            # Oddiy brauzer: Telegram Login orqali olingan HttpOnly cookie sessiyasi.
            # CSRF: cookie SameSite=Strict + boshqa saytdan yuborib bo'lmaydigan maxsus sarlavha.
            if request.headers.get("X-Requested-With") != "fetch":
                raise ApiError(401, "no_auth")
            user = await webauth.session_user(request.cookies.get(webauth.COOKIE, ""))
            if not user:
                raise ApiError(401, "no_auth")
            lang = (request.headers.get("Accept-Language") or "uz")[:2]
        request["user"] = user
        request["lang"] = lang
        if user["role"] in ("pending", "blocked") and request.path != "/api/me":
            raise ApiError(403, user["role"])
        await presence.touch(user["id"], "app" if auth.startswith("tma ") else "web")
        return await handler(request)
    except ApiError as ex:
        return web.json_response({"error": ex.code, "message": ex.message}, status=ex.status,
                                 dumps=lambda o: json.dumps(o, ensure_ascii=False))
    except web.HTTPException:
        raise
    except Exception:
        log.exception("API xato: %s %s", request.method, request.path)
        return web.json_response({"error": "server"}, status=500)


routes = web.RouteTableDef()
PUBLIC_API = {"/api/auth/config", "/api/auth/telegram"}


# ---------------------------------------------------------------- brauzer orqali kirish
def _is_https(request: web.Request) -> bool:
    return request.secure or request.headers.get("X-Forwarded-Proto") == "https"


@routes.get("/api/auth/config")
async def auth_config(request: web.Request):
    return ok({"bot_username": request.app.get(BOT_NAME_KEY, "")})


@routes.post("/api/auth/telegram")
async def auth_telegram(request: web.Request):
    if request.headers.get("X-Requested-With") != "fetch":
        raise ApiError(400, "bad_auth")
    data = await body(request)
    try:
        # Imzo Telegram yuborgan barcha maydonlar bo'yicha hisoblanadi, shuning uchun hammasini uzatamiz
        f = webauth.verify_login({k: v for k, v in data.items() if isinstance(v, (str, int)) and not isinstance(v, bool)})
    except ValueError as ex:
        raise ApiError(401, str(ex))
    uid = int(f["id"])
    full_name = " ".join(x for x in (f.get("first_name"), f.get("last_name")) if x) or str(uid)
    user, is_new = await db.upsert_user(uid, full_name, f.get("username"))
    if is_new and user["role"] == "pending":
        await services.notify_new_user(request.app[BOT_KEY], uid, full_name, f.get("username"))
    if user["role"] == "blocked":
        raise ApiError(403, "blocked")
    token = await webauth.create_session(uid, request.headers.get("User-Agent", ""))
    resp = ok({"ok": True})
    resp.set_cookie(webauth.COOKIE, token, max_age=webauth.SESSION_DAYS * 86400, path="/",
                    httponly=True, secure=_is_https(request), samesite="Strict")
    log.info("Web login: %s (%s)", uid, user["role"])
    return resp


@routes.post("/api/auth/logout")
async def auth_logout(request: web.Request):
    await webauth.delete_session(request.cookies.get(webauth.COOKIE, ""))
    resp = ok()
    resp.del_cookie(webauth.COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- me
@routes.get("/api/me")
async def me(request: web.Request):
    user = request["user"]
    perms = sorted(p for p, roles in PERMS.items() if user["role"] in roles)
    if user["role"] in ("pending", "blocked"):
        return ok({"user": user, "perms": [], "currencies": [], "fields": []})
    return ok({
        "user": user,
        "perms": perms,
        "currencies": [c["code"] for c in await db.list_currencies()],
        "fields": [{k: f[k] for k in ("id", "name", "type", "options", "required", "active")}
                   for f in await db.list_fields(active_only=True)],
        "base": BASE_CURRENCY,
        "today": today().isoformat(),
        "field_types": list(FIELD_TYPES),
        "assignable_roles": allowed_roles(user),
    })


# ---------------------------------------------------------------- zayavkalar
@routes.get("/api/requests")
async def list_requests(request: web.Request):
    user = request["user"]
    scope = request.query.get("scope", "my")
    status = request.query.get("status", "all")
    if status not in ("all", "pending", "approved", "rejected", "cancelled"):
        status = "all"
    q = request.query.get("q", "")[:100]
    try:
        offset = max(0, int(request.query.get("offset", 0)))
    except ValueError:
        offset = 0
    if scope == "all":
        need(user, "view_all")
        uid = None
    else:
        uid = user["id"]
    items = await db.list_requests(uid, status, offset, PAGE, q)
    total = await db.count_requests(uid, status, q)
    _, fmap = await fields_map()
    rates, _ = await get_rates()
    counts = {}
    for st in ("all", "pending", "approved", "rejected", "cancelled"):
        counts[st] = await db.count_requests(uid, st, q)
    return ok({"items": [serialize(r, user, fmap, rates) for r in items], "total": total,
               "offset": offset, "page": PAGE, "counts": counts})


async def load_visible(request: web.Request) -> dict:
    user = request["user"]
    r = await db.get_request(req_id(request))
    if not r:
        raise ApiError(404, "not_found")
    if r["user_id"] != user["id"] and not can(user, "view_all"):
        raise ApiError(403, "forbidden")
    return r


@routes.get("/api/requests/{rid}")
async def get_request(request: web.Request):
    user = request["user"]
    r = await load_visible(request)
    fields, fmap = await fields_map()
    rates, _ = await get_rates()
    history = await db.get_history(r["id"])
    return ok({
        "request": serialize(r, user, fmap, rates),
        "fields": [{k: f[k] for k in ("id", "name", "type", "options", "required", "active")} for f in fields],
        "history": [{"action": h["action"], "details": h["details"], "by": h["full_name"], "at": h["created_at"]}
                    for h in history],
    })


@routes.post("/api/requests")
async def create_request(request: web.Request):
    user = request["user"]
    need(user, "create")
    data = await body(request)
    currencies = {c["code"] for c in await db.list_currencies()}
    core = validate_core(data, partial=False, currencies=currencies)
    raw_extra = data.get("extra") or {}
    if not isinstance(raw_extra, dict):
        raise ApiError(400, "bad_extra")
    extra = {}
    for f in await db.list_fields(active_only=True):
        v = validate_value(f, raw_extra.get(str(f["id"])))
        if v is None:
            if f["required"]:
                raise ApiError(400, "required", f["name"])
            continue
        extra[str(f["id"])] = v
    rid = await services.create_request(request.app[BOT_KEY], user, core["title"], core["amount"], core["currency"],
                                        core["needed_date"], core["comment"], extra)
    _, fmap = await fields_map()
    return ok({"request": serialize(await db.get_request(rid), user, fmap)}, status=201)


@routes.patch("/api/requests/{rid}")
async def edit_request(request: web.Request):
    user = request["user"]
    r = await load_visible(request)
    if not can_edit(user, r):
        raise ApiError(403, "not_editable")
    data = await body(request)
    currencies = {c["code"] for c in await db.list_currencies(active_only=False)}
    core = validate_core(data, partial=True, currencies=currencies)
    fields, fmap = await fields_map()
    changes, upd = [], {}
    labels = {"title": "Maqsad", "amount": "Summa", "currency": "Valyuta", "needed_date": "Kerakli sana", "comment": "Izoh"}
    for k, v in core.items():
        if r[k] != v:
            upd[k] = v
            old, new = r[k], v
            if k == "amount":
                old, new = fmt_amount(old), fmt_amount(new)
            elif k == "needed_date":
                old, new = fmt_date(old), fmt_date(new)
            changes.append((labels[k], old, new))
    if isinstance(data.get("extra"), dict):
        extra = dict(r["extra"])
        for fid, raw in data["extra"].items():
            f = fmap.get(str(fid))
            if not f:
                continue
            if f["type"] == "file" and isinstance(raw, dict) and "file_id" not in raw:
                continue  # o'zgarmagan fayl (front-end faqat nomini biladi)
            v = validate_value(f, raw)
            if v is None and f["required"] and f["active"]:
                raise ApiError(400, "required", f["name"])
            if extra.get(str(fid)) == v:
                continue
            changes.append((f["name"], fmt_field_value(f, extra.get(str(fid))), fmt_field_value(f, v)))
            if v is None:
                extra.pop(str(fid), None)
            else:
                extra[str(fid)] = v
        if extra != r["extra"]:
            upd["extra"] = extra
    await services.edit_request(request.app[BOT_KEY], user, r, upd, changes)
    rates, _ = await get_rates()
    return ok({"request": serialize(await db.get_request(r["id"]), user, fmap, rates), "changed": bool(upd)})


@routes.post("/api/requests/{rid}/{action:approve|reject|cancel|reopen}")
async def request_action(request: web.Request):
    user = request["user"]
    r = await load_visible(request)
    action = request.match_info["action"]
    bot = request.app[BOT_KEY]
    if action == "approve":
        need(user, "decide")
        done = await services.approve(bot, r["id"], user)
    elif action == "reject":
        need(user, "decide")
        reason = str((await body(request)).get("reason") or "").strip()[:500]
        done = await services.reject(bot, r["id"], user, reason)
    elif action == "cancel":
        if r["user_id"] != user["id"]:
            raise ApiError(403, "forbidden")
        done = await services.cancel(r["id"], user)
    else:
        need(user, "admin")
        done = await services.reopen(bot, r["id"], user)
    if not done:
        raise ApiError(409, "already_decided")
    _, fmap = await fields_map()
    rates, _ = await get_rates()
    return ok({"request": serialize(await db.get_request(r["id"]), user, fmap, rates)})


@routes.get("/api/requests/{rid}/file/{fid}")
async def get_file(request: web.Request):
    r = await load_visible(request)
    v = r["extra"].get(request.match_info["fid"])
    if not isinstance(v, dict) or not v.get("file_id"):
        raise ApiError(404, "not_found")
    bot = request.app[BOT_KEY]
    try:
        f = await bot.get_file(v["file_id"])
        if f.file_size and f.file_size > 20 * 1024 * 1024:
            raise ApiError(413, "too_big")
        buf = await bot.download_file(f.file_path)
    except ApiError:
        raise
    except Exception:
        raise ApiError(404, "not_found")
    name = v.get("name") or "file"
    ctype = "image/jpeg" if v.get("kind") == "photo" else _guess_type(name)
    return web.Response(body=buf.read(), content_type=ctype,
                        headers={"Cache-Control": "private, max-age=3600"})


def _guess_type(name: str) -> str:
    import mimetypes
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


@routes.post("/api/requests/{rid}/file/{fid}/send")
async def send_file_to_chat(request: web.Request):
    user = request["user"]
    r = await load_visible(request)
    v = r["extra"].get(request.match_info["fid"])
    if not isinstance(v, dict) or not v.get("file_id"):
        raise ApiError(404, "not_found")
    bot = request.app[BOT_KEY]
    caption = f"#{r['id']} · {e(v.get('name') or '')}"
    if v.get("kind") == "photo":
        await bot.send_photo(user["id"], v["file_id"], caption=caption)
    else:
        await bot.send_document(user["id"], v["file_id"], caption=caption)
    return ok()


@routes.post("/api/upload")
async def upload(request: web.Request):
    """Faylni foydalanuvchi chatiga yuborib, Telegram file_id ni olamiz (fayl Telegramda saqlanadi)."""
    user = request["user"]
    need(user, "create")
    reader = await request.multipart()
    part = await reader.next()
    if part is None or part.name != "file":
        raise ApiError(400, "no_file")
    name = re.sub(r"[\r\n]", "", part.filename or "file")[:120]
    data = await part.read(decode=False)
    if not data:
        raise ApiError(400, "no_file")
    ctype = part.headers.get("Content-Type", "")
    bot = request.app[BOT_KEY]
    inp = BufferedInputFile(bytes(data), name)
    caption = "📎 Mini App orqali biriktirildi"
    if ctype in ("image/jpeg", "image/png", "image/webp") and len(data) < 10 * 1024 * 1024:
        m = await bot.send_photo(user["id"], inp, caption=caption, disable_notification=True)
        return ok({"kind": "photo", "file_id": m.photo[-1].file_id, "name": name})
    m = await bot.send_document(user["id"], inp, caption=caption, disable_notification=True)
    return ok({"kind": "document", "file_id": m.document.file_id, "name": name})


# ---------------------------------------------------------------- bildirishnomalar (qo'ng'iroqcha)
@routes.get("/api/notifications/unread")
async def notif_unread(request: web.Request):
    return ok({"unread": await inbox.unread_count(request["user"]["id"])})


@routes.get("/api/notifications")
async def notif_list(request: web.Request):
    uid = request["user"]["id"]
    try:
        before = int(request.query.get("before") or 0) or None
    except ValueError:
        raise ApiError(400, "bad_value")
    items = await inbox.listing(uid, before)
    return ok({"items": items, "unread": await inbox.unread_count(uid), "more": len(items) == 30})


@routes.post("/api/notifications/read")
async def notif_read(request: web.Request):
    data = await body(request)
    nid = data.get("id")
    if nid is not None and (not isinstance(nid, int) or isinstance(nid, bool)):
        raise ApiError(400, "bad_value")
    await inbox.mark_read(request["user"]["id"], nid)
    return ok({"unread": await inbox.unread_count(request["user"]["id"])})


# ---------------------------------------------------------------- muddatlar
@routes.get("/api/due")
async def due(request: web.Request):
    user = request["user"]
    uid = None if can(user, "view_all") else user["id"]
    t = today()
    from datetime import timedelta
    _, fmap = await fields_map()
    rates, _ = await get_rates()
    overdue = await db.overdue_pending(t.isoformat(), uid)
    upcoming = await db.requests_due_between(t.isoformat(), (t + timedelta(days=30)).isoformat(), uid)
    return ok({"overdue": [serialize(r, user, fmap, rates) for r in overdue],
               "upcoming": [serialize(r, user, fmap, rates) for r in upcoming]})


# ---------------------------------------------------------------- analitika
@routes.get("/api/dashboard")
async def dashboard(request: web.Request):
    need(request["user"], "analytics")
    data = await reports.dashboard_data(request.query.get("period", "month"))
    # Bosh sahifa uchun "qaroringizni kutmoqda" soni — alohida so'rov yubormaslik uchun shu yerda
    data["pending_total"] = await db.count_requests(None, "pending") if can(request["user"], "decide") else 0
    return ok(data)


@routes.get("/api/summary")
async def my_summary(request: web.Request):
    """Oddiy xodim uchun bosh sahifa: o'z zayavkalari bo'yicha qisqa ma'lumot."""
    user = request["user"]
    counts = {st: await db.count_requests(user["id"], st) for st in ("all", "pending", "approved", "rejected")}
    rates, _ = await get_rates()
    approved = await db.list_requests(user["id"], "approved", 0, 1000)
    t = today().isoformat()[:7]
    month_sum = sum(req_base(r, rates) or 0 for r in approved if r["created_at"][:7] == t)
    return ok({"counts": counts, "approved_month": round(month_sum, 2), "base": BASE_CURRENCY})


@routes.post("/api/export")
async def export(request: web.Request):
    user = request["user"]
    need(user, "analytics")
    period = (await body(request)).get("period", "month")
    if period not in reports.PERIODS:
        period = "month"
    data = await reports.excel(period)
    name = f"zayavkalar_{period}_{today().strftime('%Y%m%d')}.xlsx"
    await request.app[BOT_KEY].send_document(user["id"], BufferedInputFile(data, name),
                                             caption=f"📥 Zayavkalar — {reports.PERIODS[period]}")
    return ok()


# ---------------------------------------------------------------- admin
@routes.get("/api/admin/users")
async def admin_users(request: web.Request):
    need(request["user"], "admin")
    items = await db.list_users(0, 1000)
    now = int(time.time())
    for u in items:
        u["online"] = presence.is_online(u.get("last_seen"), now)
    return ok({"items": items, "now": now, "online": sum(u["online"] for u in items)})


@routes.post("/api/admin/users/{uid}/role")
async def admin_set_role(request: web.Request):
    me_ = request["user"]
    need(me_, "admin")
    uid = int(request.match_info["uid"])
    role = (await body(request)).get("role")
    target = await db.get_user(uid)
    if not target:
        raise ApiError(404, "not_found")
    err = role_change_error(me_, target, role)
    if err:
        raise ApiError(400 if err == "bad_role" else 403, err)
    await services.set_role(request.app[BOT_KEY], me_, target, role)
    return ok({"user": await db.get_user(uid)})


@routes.get("/api/admin/fields")
async def admin_fields(request: web.Request):
    need(request["user"], "admin")
    return ok({"items": await db.list_fields()})


def _options(raw) -> list[str]:
    if isinstance(raw, str):
        raw = re.split(r"[\n,;]", raw)
    if not isinstance(raw, list):
        return []
    seen, out = set(), []
    for o in raw:
        o = str(o).strip()[:40]
        if o and o.lower() not in seen:
            seen.add(o.lower())
            out.append(o)
    return out[:30]


@routes.post("/api/admin/fields")
async def admin_add_field(request: web.Request):
    need(request["user"], "admin")
    data = await body(request)
    name = str(data.get("name") or "").strip()
    ftype = data.get("type")
    if not 1 <= len(name) <= 60 or ftype not in FIELD_TYPES:
        raise ApiError(400, "bad_field")
    opts = _options(data.get("options")) if ftype == "choice" else []
    if ftype == "choice" and len(opts) < 2:
        raise ApiError(400, "need_options")
    fid = await services.add_field(request["user"], name, ftype, opts, bool(data.get("required")))
    return ok({"field": await db.get_field(fid)}, status=201)


@routes.patch("/api/admin/fields/{fid}")
async def admin_edit_field(request: web.Request):
    need(request["user"], "admin")
    fid = int(request.match_info["fid"])
    f = await db.get_field(fid)
    if not f:
        raise ApiError(404, "not_found")
    data = await body(request)
    upd = {}
    if "name" in data:
        name = str(data["name"]).strip()
        if not 1 <= len(name) <= 60:
            raise ApiError(400, "bad_field")
        upd["name"] = name
    if "required" in data:
        upd["required"] = int(bool(data["required"]))
    if "active" in data:
        upd["active"] = int(bool(data["active"]))
    if "options" in data and f["type"] == "choice":
        opts = _options(data["options"])
        if len(opts) < 2:
            raise ApiError(400, "need_options")
        upd["options"] = opts
    if upd:
        await services.update_field(request["user"], f, **upd)
    if data.get("move") == "up":
        await services.move_field_up(request["user"], f)
    return ok({"field": await db.get_field(fid)})


@routes.delete("/api/admin/fields/{fid}")
async def admin_delete_field(request: web.Request):
    need(request["user"], "admin")
    f = await db.get_field(int(request.match_info["fid"]))
    if f:
        await services.delete_field(request["user"], f)
    return ok()


@routes.get("/api/admin/currencies")
async def admin_currencies(request: web.Request):
    need(request["user"], "admin")
    return ok({"items": await db.list_currencies(active_only=False)})


@routes.post("/api/admin/currencies")
async def admin_add_currency(request: web.Request):
    need(request["user"], "admin")
    code = str((await body(request)).get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ApiError(400, "bad_currency")
    await services.add_currency(request["user"], code)
    return ok({"items": await db.list_currencies(active_only=False)})


@routes.post("/api/admin/currencies/{code}/toggle")
async def admin_toggle_currency(request: web.Request):
    need(request["user"], "admin")
    code = request.match_info["code"].upper()
    active = await db.list_currencies(active_only=True)
    if len(active) == 1 and active[0]["code"] == code:
        raise ApiError(400, "last_currency")
    await services.toggle_currency(request["user"], code)
    return ok({"items": await db.list_currencies(active_only=False)})


# ---------------------------------------------------------------- kunlik kurslar
def _day_param(raw: str | None) -> str:
    try:
        d = date.fromisoformat(str(raw or today().isoformat())[:10])
    except ValueError:
        raise ApiError(400, "bad_date")
    if d > today():
        raise ApiError(400, "future_date")
    return d.isoformat()


@routes.get("/api/rates/today")
async def rates_today(request: web.Request):
    """Zayavka formasi uchun (faqat o'qish): bugungi yoki tahrirlanayotgan zayavka kuni kurslari.
    Har kim ko'radi — valyuta tanlaganda kurs va kim qo'ygani ko'rsatiladi."""
    need(request["user"], "create")
    day = _day_param(request.query.get("day"))
    return ok({"day": day, "today": today().isoformat(), "items": await rates_mod.day_rates(day)})


@routes.get("/api/rates")
async def rates_day(request: web.Request):
    need(request["user"], "rates_view")
    day = _day_param(request.query.get("day"))
    return ok({"day": day, "today": today().isoformat(), "items": await rates_mod.day_rates(day),
               "can_edit": can(request["user"], "rates_edit")})


@routes.get("/api/rates/history")
async def rates_history(request: web.Request):
    need(request["user"], "rates_view")
    code = str(request.query.get("code") or "USD").upper()[:3]
    return ok({"code": code, "items": await rates_mod.history(code, 60)})


async def _rate_target(request: web.Request) -> tuple[str, str]:
    need(request["user"], "rates_edit")
    day = _day_param(request.match_info["day"])
    code = request.match_info["code"].upper()
    if code not in {c["code"] for c in await db.list_currencies(active_only=False)} or code == "UZS":
        raise ApiError(400, "bad_currency")
    return day, code


@routes.put("/api/rates/{day}/{code}")
async def rates_set(request: web.Request):
    """Qo'lda kurs (tasdiqlovchi, admin, super admin). Qulflanadi — API ustidan yozmaydi."""
    day, code = await _rate_target(request)
    try:
        rate = round(float((await body(request)).get("rate")), 6)
    except (TypeError, ValueError):
        raise ApiError(400, "bad_rate")
    if not 0 < rate < 1e9:
        raise ApiError(400, "bad_rate")
    await rates_mod.set_manual(request["user"], day, code, rate)
    return ok({"day": day, "items": await rates_mod.day_rates(day)})


@routes.post("/api/rates/{day}/{code}/auto")
async def rates_unlock(request: web.Request):
    """Qo'lda kursni bekor qilib, avtomatik yangilanishga qaytaradi."""
    day, code = await _rate_target(request)
    if not await rates_mod.set_auto(request["user"], day, code):
        raise ApiError(409, "no_change")
    return ok({"day": day, "items": await rates_mod.day_rates(day)})


# ---------------------------------------------------------------- audit log
def _audit_row(r: dict) -> dict:
    return {k: r[k] for k in ("id", "created_at", "actor_id", "actor_name", "entity", "entity_id", "entity_label",
                              "action", "field", "old_value", "new_value", "deleted", "deleted_at", "restored_at")}


@routes.get("/api/audit")
async def audit_list(request: web.Request):
    """Admin: faol yozuvlar. Super admin: o'chirilganlar (deleted=Y) ham."""
    user = request["user"]
    need(user, "admin")
    deleted = request.query.get("deleted", "N")
    if deleted not in ("N", "Y", "all"):
        deleted = "N"
    if deleted != "N":
        need(user, "manage_admins")
    try:
        offset = max(0, int(request.query.get("offset", 0)))
    except ValueError:
        offset = 0
    rows, total = await audit.query(request.query.get("entity") or None, deleted, request.query.get("q", "")[:100],
                                    request.query.get("entity_id") or None, offset, 30)
    return ok({"items": [_audit_row(r) for r in rows], "total": total, "offset": offset, "page": 30,
               "retention_days": audit.RETENTION_DAYS})


@routes.post("/api/audit/{lid}/restore")
async def audit_restore(request: web.Request):
    """Super admin: 3 oydan keyin avtomatik deleted='Y' bo'lgan yozuvni tiklaydi (N).
    Tarixni qo'lda o'chirish (Y qilish) imkoniyati ataylab yo'q."""
    user = request["user"]
    need(user, "manage_admins")
    if not await audit.restore(int(request.match_info["lid"]), user):
        raise ApiError(409, "no_change")
    row = await db.fetchone("SELECT * FROM audit_log WHERE id=?", int(request.match_info["lid"]))
    return ok({"item": _audit_row(row)})


# ---------------------------------------------------------------- statik
def _asset_version(match: re.Match) -> str:
    path = STATIC_DIR / "static" / match.group(1)
    try:
        v = int(path.stat().st_mtime)
    except OSError:
        v = 0
    return f"/static/{match.group(1)}?v={v}"


async def index(request: web.Request):
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"/static/([\w.-]+)\?v=\w+", _asset_version, html)
    return web.Response(text=html, content_type="text/html")


def build_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[auth_mw], client_max_size=20 * 1024 * 1024)
    app[BOT_KEY] = bot
    app.add_routes(routes)
    app.router.add_get("/", index)
    app.router.add_static("/static/", STATIC_DIR / "static", append_version=False)
    return app


async def start_web(bot: Bot) -> web.AppRunner:
    app = build_app(bot)
    try:  # brauzerdagi "Telegram orqali kirish" tugmasi uchun bot nomi
        app[BOT_NAME_KEY] = (await bot.get_me()).username or ""
    except Exception:
        log.warning("Bot username olinmadi — brauzer orqali kirish tugmasi ko'rinmaydi", exc_info=True)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    log.info("Mini App serveri: http://%s:%s", WEB_HOST, WEB_PORT)
    return runner
