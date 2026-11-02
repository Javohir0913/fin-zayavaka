"""Admin qo'shgan qo'shimcha maydonlarni (custom fields) so'rash va tekshirish."""
from aiogram.types import Message

from .keyboards import abort_row, btn, date_rows, ikb
from .utils import e, parse_date, parse_number


async def ask_field(msg: Message, field: dict, prefix: str, editing: bool = False) -> None:
    t = field["type"]
    req = field["required"]
    head = f"🧩 <b>{e(field['name'])}</b>" + ("" if req else " <i>(ixtiyoriy)</i>")
    rows = []
    if t == "choice":
        rows = [[btn(opt, f"{prefix}:o:{i}")] for i, opt in enumerate(field["options"])]
        hint = "Variantni tanlang:"
    elif t == "bool":
        rows = [[btn("✅ Ha", f"{prefix}:b:1"), btn("❌ Yo'q", f"{prefix}:b:0")]]
        hint = "Tanlang:"
    elif t == "date":
        rows = date_rows(f"{prefix}:d")
        hint = "Sanani tanlang yoki yozing (KK.OO.YYYY):"
    elif t == "number":
        hint = "Raqam kiriting:"
    elif t == "file":
        hint = "Rasm yoki fayl yuboring:"
    else:
        hint = "Matn kiriting:"
    if not req:
        rows.append([btn("🧹 Bo'sh qoldirish" if editing else "⏭ O'tkazib yuborish", f"{prefix}:s:")])
    if editing:
        rows.append(abort_row())
    await msg.answer(f"{head}\n{hint}", reply_markup=ikb(rows) if rows else None)


def parse_field_callback(field: dict, data: str) -> tuple[bool, object]:
    """data: '<prefix>:<kind>:<payload>'. (ok, qiymat yoki xato matni)."""
    try:
        _, kind, payload = data.split(":", 2)
    except ValueError:
        return False, "Noto'g'ri tanlov"
    if kind == "s":
        return (False, "Bu maydon majburiy") if field["required"] else (True, None)
    if kind == "o" and field["type"] == "choice":
        try:
            return True, field["options"][int(payload)]
        except (ValueError, IndexError):
            return False, "Variant topilmadi (maydon o'zgargan bo'lishi mumkin)"
    if kind == "b" and field["type"] == "bool":
        return True, payload == "1"
    if kind == "d" and field["type"] == "date":
        return True, payload
    return False, "Noto'g'ri tanlov"


def parse_field_message(field: dict, message: Message) -> tuple[bool, object]:
    t = field["type"]
    if t == "file":
        if message.photo:
            return True, {"kind": "photo", "file_id": message.photo[-1].file_id, "name": "rasm"}
        if message.document:
            return True, {"kind": "document", "file_id": message.document.file_id,
                          "name": message.document.file_name or "fayl"}
        return False, "Iltimos, rasm yoki fayl yuboring."
    text = (message.text or "").strip()
    if not text:
        return False, "Iltimos, matn yuboring."
    if t == "number":
        v = parse_number(text)
        return (True, v) if v is not None else (False, "Raqam noto'g'ri. Masalan: 15 yoki 2500.50")
    if t == "date":
        d = parse_date(text)
        return (True, d.isoformat()) if d else (False, "Sana noto'g'ri. Format: KK.OO.YYYY")
    if t == "choice":
        for opt in field["options"]:
            if opt.lower() == text.lower():
                return True, opt
        return False, "Tugmalardan birini tanlang."
    if t == "bool":
        low = text.lower()
        if low in ("ha", "xa", "yes", "да", "1", "+"):
            return True, True
        if low in ("yo'q", "yoq", "yo‘q", "no", "нет", "0", "-"):
            return True, False
        return False, "Ha yoki Yo'q ni tanlang."
    if len(text) > 1000:
        return False, "Matn juda uzun (maks. 1000 belgi)."
    return True, text
