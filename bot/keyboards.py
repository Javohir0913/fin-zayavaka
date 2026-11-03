from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup, WebAppInfo)

from .config import WEBAPP_URL
from .render import list_line
from .utils import ASSIGNABLE_ROLES, ROLES, STATUS_EMOJI, can, quick_dates

BTN_NEW = "➕ Yangi zayavka"
BTN_MY = "📋 Mening zayavkalarim"
BTN_ALL = "📂 Barcha zayavkalar"
BTN_PENDING = "⏳ Kutilayotganlar"
BTN_DUE = "📅 Muddatlar"
BTN_DASH = "📊 Dashboard"
BTN_REPORT = "📝 Qisqa hisobot"
BTN_ADMIN = "⚙️ Admin panel"
BTN_CANCEL = "❌ Bekor qilish"

BTN_APP = "📱 Ilovani ochish"
MENU_BUTTONS = {BTN_NEW, BTN_MY, BTN_ALL, BTN_PENDING, BTN_DUE, BTN_DASH, BTN_REPORT, BTN_ADMIN, BTN_APP}


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def ikb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def main_menu(user: dict) -> ReplyKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        # Oddiy klaviatura tugmasidan ochilgan Mini App initData olmaydi — shuning uchun bu tugma
        # inline web_app tugmasini yuboradi (app_link_kb)
        rows.append([KeyboardButton(text=BTN_APP)])
    rows.append([KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_MY)])
    if can(user, "view_all"):
        rows.append([KeyboardButton(text=BTN_ALL), KeyboardButton(text=BTN_PENDING)])
    row = [KeyboardButton(text=BTN_DUE)]
    if can(user, "analytics"):
        row.append(KeyboardButton(text=BTN_REPORT))
    rows.append(row)
    if can(user, "analytics"):
        rows.append([KeyboardButton(text=BTN_DASH)])
    if can(user, "admin"):
        rows[-1].append(KeyboardButton(text=BTN_ADMIN))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def app_link_kb() -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL:
        return None
    return ikb([[InlineKeyboardButton(text="📱 Ilovani ochish", web_app=WebAppInfo(url=WEBAPP_URL))]])


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def abort_row() -> list[InlineKeyboardButton]:
    return [btn("✖️ Bekor", "ex")]


def currency_kb(currencies: list[dict], prefix: str, with_abort: bool = False) -> InlineKeyboardMarkup:
    codes = [c["code"] for c in currencies]
    rows = [[btn(c, f"{prefix}:{c}") for c in codes[i:i + 4]] for i in range(0, len(codes), 4)]
    if with_abort:
        rows.append(abort_row())
    return ikb(rows)


def date_rows(prefix: str) -> list[list[InlineKeyboardButton]]:
    q = quick_dates()
    b = [btn(f"{label} ({d.strftime('%d.%m')})", f"{prefix}:{d.isoformat()}") for label, d in q]
    return [b[:2], b[2:]]


def date_kb(prefix: str, with_abort: bool = False) -> InlineKeyboardMarkup:
    rows = date_rows(prefix)
    if with_abort:
        rows.append(abort_row())
    return ikb(rows)


def decision_kb(rid: int) -> InlineKeyboardMarkup:
    return ikb([
        [btn("✅ Tasdiqlash", f"rq:ap:{rid}"), btn("❌ Rad etish", f"rq:rj:{rid}")],
        [btn("🔎 Batafsil", f"rq:v:{rid}")],
    ])


def card_kb(req: dict, user: dict, has_files: bool) -> InlineKeyboardMarkup:
    rid = req["id"]
    is_author = req["user_id"] == user["id"]
    rows = []
    if req["status"] == "pending" and can(user, "decide"):
        rows.append([btn("✅ Tasdiqlash", f"rq:ap:{rid}"), btn("❌ Rad etish", f"rq:rj:{rid}")])
    r2 = []
    if can(user, "admin") or (is_author and req["status"] == "pending"):
        r2.append(btn("✏️ Tahrirlash", f"rq:ed:{rid}"))
    if is_author and req["status"] == "pending":
        r2.append(btn("🚫 Bekor qilish", f"rq:cn:{rid}"))
    if can(user, "admin") and req["status"] != "pending":
        r2.append(btn("↩️ Kutishga qaytarish", f"rq:rp:{rid}"))
    rows.append(r2)
    r3 = [btn("🕓 Tarix", f"rq:h:{rid}"), btn("🔄 Yangilash", f"rq:rf:{rid}")]
    if has_files:
        r3.append(btn("📎 Fayllar", f"rq:f:{rid}"))
    rows.append(r3)
    return ikb(rows)


STATUS_FILTERS = [("all", "Hammasi"), ("pending", "⏳"), ("approved", "✅"), ("rejected", "❌"), ("cancelled", "🚫")]


def list_kb(items: list[dict], scope: str, status: str, page: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    rows = [[
        btn(("• " if s == status else "") + label, f"ls:{scope}:{s}:0") for s, label in STATUS_FILTERS
    ]]
    for r in items:
        rows.append([btn(list_line(r, with_author=scope == "all"), f"rq:v:{r['id']}")])
    pages = max(1, (total + page_size - 1) // page_size)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(btn("⬅️", f"ls:{scope}:{status}:{page - 1}"))
        nav.append(btn(f"{page + 1}/{pages}", "noop"))
        if page < pages - 1:
            nav.append(btn("➡️", f"ls:{scope}:{status}:{page + 1}"))
        rows.append(nav)
    return ikb(rows)


def role_assign_kb(uid: int, roles: list[str] | None = None) -> InlineKeyboardMarkup:
    b = [btn(ROLES[r], f"adm:r:{uid}:{r}") for r in (roles or ASSIGNABLE_ROLES)]
    return ikb([b[i:i + 2] for i in range(0, len(b), 2)])


def yes_no_kb(yes: str, no: str) -> InlineKeyboardMarkup:
    return ikb([[btn("✅ Ha", yes), btn("❌ Yo'q", no)]])


def status_emoji(s: str) -> str:
    return STATUS_EMOJI.get(s, "")
