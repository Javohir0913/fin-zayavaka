"""Zayavka kartochkalari va qiymatlarni matnga aylantirish."""
from .utils import (STATUS, STATUS_EMOJI, due_hint, e, fmt_amount, fmt_date, fmt_dt, short)


def fmt_field_value(field: dict, value) -> str:
    t = field["type"]
    if value is None or value == "":
        return "—"
    if t == "number":
        return fmt_amount(value)
    if t == "date":
        return fmt_date(value)
    if t == "bool":
        return "✅ Ha" if value else "❌ Yo'q"
    if t == "file":
        name = value.get("name") if isinstance(value, dict) else None
        return "📎 " + (e(name) if name else "biriktirilgan")
    return e(value)


def field_plain(field: dict, value) -> str:
    """Excel uchun oddiy matn."""
    t = field["type"]
    if value is None:
        return ""
    if t == "bool":
        return "Ha" if value else "Yo'q"
    if t == "date":
        return fmt_date(value)
    if t == "file":
        return (value.get("name") or "fayl") if isinstance(value, dict) else "fayl"
    return value


def render_body(title: str, amount: float, currency: str, needed_date: str, comment: str,
                extra: dict, fields: list[dict], status: str | None = None) -> list[str]:
    lines = [
        f"🎯 Maqsad: {e(title)}",
        f"💰 Summa: <b>{fmt_amount(amount)} {e(currency)}</b>",
        f"📅 Kerakli sana: <b>{fmt_date(needed_date)}</b> {due_hint(needed_date, status)}".rstrip(),
    ]
    if comment:
        lines.append(f"💬 Izoh: {e(comment)}")
    custom = [
        f"▫️ {e(f['name'])}: {fmt_field_value(f, extra[str(f['id'])])}"
        for f in fields if str(f["id"]) in extra
    ]
    if custom:
        lines.append("")
        lines += custom
    return lines


def render_card(req: dict, fields: list[dict]) -> str:
    lines = [
        f"📄 <b>Zayavka #{req['id']}</b>",
        f"Holat: <b>{STATUS.get(req['status'], req['status'])}</b>",
        "",
        f"👤 Muallif: {e(req.get('author_name'))}",
    ]
    lines += render_body(req["title"], req["amount"], req["currency"], req["needed_date"],
                         req["comment"], req["extra"], fields, req["status"])
    rl = rate_line(req)
    if rl:
        lines.insert(lines.index(next(x for x in lines if x.startswith("💰"))) + 1, rl)
    lines.append("")
    lines.append(f"🕒 Yaratildi: {fmt_dt(req['created_at'])}")
    if req["status"] == "approved":
        lines.append(f"✅ Tasdiqladi: {e(req.get('decider_name'))} · {fmt_dt(req['decided_at'])}")
    elif req["status"] == "rejected":
        lines.append(f"❌ Rad etdi: {e(req.get('decider_name'))} · {fmt_dt(req['decided_at'])}")
        if req["reject_reason"]:
            lines.append(f"📌 Sabab: {e(req['reject_reason'])}")
    elif req["status"] == "cancelled":
        lines.append(f"🚫 Bekor qilindi: {fmt_dt(req['decided_at'])}")
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3990] + "…"


def list_line(req: dict, with_author: bool) -> str:
    """Ro'yxatdagi tugma matni."""
    s = f"{STATUS_EMOJI[req['status']]} #{req['id']} · {fmt_amount(req['amount'])} {req['currency']} · {fmt_date(req['needed_date'])[:5]}"
    if with_author:
        s += f" · {short(req.get('author_name') or '', 14)}"
    return s


def text_line(req: dict, with_author: bool = True) -> str:
    """Hisobotlar ichidagi qator (/r12 - bosiladigan buyruq)."""
    s = f"{STATUS_EMOJI[req['status']]} /r{req['id']} <b>{fmt_amount(req['amount'])} {req['currency']}</b> — {e(short(req['title'], 40))}"
    if with_author:
        s += f" <i>({e(short(req.get('author_name') or '', 20))})</i>"
    return s


def rate_line(req: dict) -> str:
    """'💱 Kurs: 1 USD = 11 941,65 so'm (03.11.2026) · ✋ qo'lda: Ism' — UZS bo'lmagan zayavkalar uchun."""
    if req.get("currency") == "UZS" or not req.get("rate"):
        return ""
    who = f"✋ qo'lda: {e(req.get('rate_set_by') or '—')}" if req.get("rate_manual") else f"avto · {e(req.get('rate_source') or '')}"
    base = req["amount"] * req["rate"]
    return (f"💱 Kurs: 1 {e(req['currency'])} = {fmt_amount(req['rate'])} so'm ({fmt_date(req.get('rate_used_day'))}) · {who}\n"
            f"     ≈ <b>{fmt_amount(round(base))} UZS</b>")
