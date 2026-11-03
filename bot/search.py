"""Umumiy qidiruv: zayavkalar va audit log uchun bitta qoida.

- Katta/kichik harf farqi yo'q — kirill harflarida ham (SQLite LIKE faqat lotinda farqlamaydi)
- O'zbekcha apostroflar bir xil: o' = o‘ = oʻ = o’ = o`
- Raqamlar: "2 500 000" = "2,500,000" = "2500000"
- Bir nechta so'z: har bir so'z istalgan maydonda bo'lishi kifoya (tartib muhim emas): "ofis printer"
- "#12" — aynan 12-ID
"""
import json
import re

_APOS = str.maketrans({c: "'" for c in "‘’ʻʼ`´′‛"})
_DIGIT_GROUP = re.compile(r"(?<=\d)[\s  ,](?=\d{3}(?!\d))")
_TRAIL_ZERO = re.compile(r"(\d)\.0+(?!\d)")
_WS = re.compile(r"\s+")


def norm(value) -> str:
    """SQLite ga `norm(x)` sifatida ro'yxatdan o'tkaziladi."""
    if value is None:
        return ""
    s = str(value).translate(_APOS).lower()
    s = _DIGIT_GROUP.sub("", s)          # 2 500 000 -> 2500000
    s = _DIGIT_GROUP.sub("", s)          # ketma-ket guruhlar uchun ikkinchi o'tish
    s = _TRAIL_ZERO.sub(r"\1", s)        # 2500000.0 -> 2500000
    return _WS.sub(" ", s)


def json_values(raw) -> str:
    """Qo'shimcha maydonlar JSON idan faqat qiymatlarni oladi (kalitlar — maydon ID lari — qidiruvga kirmasin)."""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    out = []
    for v in (data.values() if isinstance(data, dict) else []):
        if isinstance(v, dict):
            out.append(str(v.get("name") or ""))
        elif isinstance(v, bool):
            out.append("ha yes да" if v else "yo'q no нет")
        else:
            out.append(str(v))
    return " ".join(out)


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def terms(q: str) -> list[str]:
    q = norm((q or "").strip())[:100]
    return [t for t in q.split(" ") if t][:8]


def build(q: str, haystack_sql: str, id_sql: str) -> tuple[str, list]:
    """Har bir so'z uchun shart (AND). haystack_sql — norm() qilinadigan matn ifodasi."""
    conds, args = [], []
    for t in terms(q):
        if t.startswith("#") and t[1:].isdigit():
            conds.append(f"{id_sql} = ?")
            args.append(t[1:])
        elif t.isdigit():
            conds.append(f"({id_sql} = ? OR norm({haystack_sql}) LIKE ? ESCAPE '\\')")
            args += [t, f"%{_like_escape(t)}%"]
        else:
            conds.append(f"norm({haystack_sql}) LIKE ? ESCAPE '\\'")
            args.append(f"%{_like_escape(t)}%")
    return " AND ".join(conds), args


REQUEST_HAYSTACK = (
    "(r.title || ' ' || r.comment || ' ' || COALESCE(u.full_name,'') || ' ' || COALESCE(u.username,'') || ' ' || "
    "r.currency || ' ' || CAST(r.amount AS TEXT) || ' ' || json_values(r.extra) || ' ' || r.reject_reason)"
)
AUDIT_HAYSTACK = (
    "(actor_name || ' ' || entity_label || ' ' || field || ' ' || COALESCE(old_value,'') || ' ' || "
    "COALESCE(new_value,'') || ' ' || action)"
)
