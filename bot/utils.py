import html
from datetime import date, datetime, timedelta

from .config import TZ

STATUS = {
    "pending": "⏳ Kutilmoqda",
    "approved": "✅ Tasdiqlangan",
    "rejected": "❌ Rad etilgan",
    "cancelled": "🚫 Bekor qilingan",
}
STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "rejected": "❌", "cancelled": "🚫"}

ROLES = {
    "admin": "👑 Admin",
    "approver": "🛡 Tasdiqlovchi",
    "viewer": "👁 Kuzatuvchi (buxgalter)",
    "user": "👤 Xodim",
    "pending": "🕓 Ruxsat kutmoqda",
    "blocked": "⛔ Bloklangan",
}
ASSIGNABLE_ROLES = ["user", "approver", "viewer", "admin", "blocked"]

# Rol -> ruxsatlar
PERMS = {
    "create": {"user", "approver", "viewer", "admin"},
    "view_all": {"approver", "viewer", "admin"},
    "decide": {"approver", "admin"},
    "analytics": {"approver", "viewer", "admin"},
    "admin": {"admin"},
}

FIELD_TYPES = {
    "text": "📝 Matn",
    "number": "🔢 Raqam",
    "date": "📅 Sana",
    "choice": "🔘 Tanlov (ro'yxat)",
    "bool": "☑️ Ha / Yo'q",
    "file": "📎 Fayl / rasm",
}

HISTORY_ACTIONS = {
    "created": "🆕 Yaratildi",
    "edited": "✏️ Tahrirlandi",
    "approved": "✅ Tasdiqlandi",
    "rejected": "❌ Rad etildi",
    "cancelled": "🚫 Bekor qilindi",
    "reopened": "↩️ Kutishga qaytarildi",
}


def can(user: dict | None, perm: str) -> bool:
    return bool(user) and user["role"] in PERMS.get(perm, set())


def e(value) -> str:
    return "" if value is None else html.escape(str(value), quote=False)


def today() -> date:
    return datetime.now(TZ).date()


def now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fmt_amount(v) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.2f}".replace(",", " ")
    if s.endswith(".00"):
        s = s[:-3]
    return s


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def fmt_dt(s: str | None) -> str:
    dt = parse_dt(s)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"


def due_hint(iso: str, status: str | None = None) -> str:
    if status not in (None, "pending", "approved"):
        return ""
    try:
        delta = (date.fromisoformat(iso) - today()).days
    except ValueError:
        return ""
    if delta == 0:
        return "(bugun)"
    if delta == 1:
        return "(ertaga)"
    if delta > 1:
        return f"({delta} kun qoldi)"
    return f"(⚠️ {-delta} kun o'tdi)"


def parse_number(text: str, allow_zero: bool = True) -> float | None:
    t = (text or "").strip().replace(" ", "").replace(" ", "").replace("'", "")
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif t.count(",") > 1:
        t = t.replace(",", "")
    else:
        t = t.replace(",", ".")
    if t.count(".") > 1:  # 1.500.000
        t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    if v != v or abs(v) > 1e15:  # NaN / juda katta
        return None
    if v < 0 or (v == 0 and not allow_zero):
        return None
    return round(v, 2)


def parse_amount(text: str) -> float | None:
    return parse_number(text, allow_zero=False)


def parse_date(text: str) -> date | None:
    t = (text or "").strip().replace(" ", "")
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    try:  # 05.11 -> joriy yil
        d = datetime.strptime(t, "%d.%m").date()
        return d.replace(year=today().year)
    except ValueError:
        return None


def quick_dates() -> list[tuple[str, date]]:
    t = today()
    return [
        ("Bugun", t),
        ("Ertaga", t + timedelta(days=1)),
        ("3 kundan keyin", t + timedelta(days=3)),
        ("1 haftadan keyin", t + timedelta(days=7)),
    ]


def short(text: str, n: int = 30) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"
