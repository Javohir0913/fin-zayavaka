"""Dashboard, analitika, grafiklar, Excel va qisqa hisobot."""
import io
from collections import defaultdict
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from . import db  # noqa: E402
from .config import BASE_CURRENCY  # noqa: E402
from .rates import get_rates, req_base  # noqa: E402
from .render import field_plain, text_line  # noqa: E402
from .utils import (STATUS, e, fmt_amount, fmt_date, parse_dt, short, today)  # noqa: E402

PERIODS = {
    "today": "Bugun",
    "week": "Shu hafta",
    "month": "Shu oy",
    "pmonth": "O'tgan oy",
    "year": "Shu yil",
    "all": "Butun davr",
}
STATUS_ORDER = ["approved", "pending", "rejected", "cancelled"]
STATUS_COLORS = {"approved": "#2e9e5b", "pending": "#e0a800", "rejected": "#d64545", "cancelled": "#9aa0a6"}


def period_range(period: str) -> tuple[date | None, date | None]:
    t = today()
    if period == "today":
        return t, t
    if period == "week":
        return t - timedelta(days=t.weekday()), t
    if period == "month":
        return t.replace(day=1), t
    if period == "pmonth":
        end = t.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if period == "year":
        return t.replace(month=1, day=1), t
    return None, None


async def _rows(period: str) -> list[dict]:
    start, end = period_range(period)
    return await db.requests_created_between(start and start.isoformat(), end and end.isoformat())


def _period_label(period: str) -> str:
    start, end = period_range(period)
    if not start:
        return PERIODS[period]
    if start == end:
        return f"{PERIODS[period]} ({start.strftime('%d.%m.%Y')})"
    return f"{PERIODS[period]} ({start.strftime('%d.%m')}–{end.strftime('%d.%m.%Y')})"


class Stats:
    """Bir davr bo'yicha hisoblangan ko'rsatkichlar."""

    def __init__(self, rows: list[dict], rates: dict[str, float]):
        self.rows = rows
        self.count = defaultdict(int)                    # status -> soni
        self.by_cur = defaultdict(lambda: defaultdict(float))  # cur -> status -> summa
        self.base = defaultdict(float)                   # status -> UZS ekv.
        self.missing_rates: set[str] = set()
        self.by_user = defaultdict(lambda: [0, 0.0, ""])  # uid -> [soni, UZS, ism]
        decide_hours = []
        for r in rows:
            st = r["status"]
            self.count[st] += 1
            self.by_cur[r["currency"]][st] += r["amount"]
            v = req_base(r, rates)
            if v is None:
                self.missing_rates.add(r["currency"])
            else:
                r["_base"] = v
                self.base[st] += v
            if st != "cancelled":
                u = self.by_user[r["user_id"]]
                u[0] += 1
                u[1] += v or 0
                u[2] = r.get("author_name") or str(r["user_id"])
            if st in ("approved", "rejected"):
                a, b = parse_dt(r["created_at"]), parse_dt(r["decided_at"])
                if a and b:
                    decide_hours.append((b - a).total_seconds() / 3600)
        self.total = len(rows)
        decided = self.count["approved"] + self.count["rejected"]
        self.approval_rate = (self.count["approved"] / decided * 100) if decided else None
        self.avg_decide_h = sum(decide_hours) / len(decide_hours) if decide_hours else None
        requested = [r["_base"] for r in rows if "_base" in r and r["status"] != "cancelled"]
        self.avg_amount = sum(requested) / len(requested) if requested else None


def _hours(h: float) -> str:
    if h < 1:
        return f"{int(h * 60)} daqiqa"
    if h < 48:
        return f"{h:.1f} soat"
    return f"{h / 24:.1f} kun"


async def dashboard_text(period: str) -> str:
    rows = await _rows(period)
    rates, rate_date = await get_rates()
    s = Stats(rows, rates)
    c = s.count
    lines = [f"📊 <b>Dashboard — {_period_label(period)}</b>", ""]
    if not rows:
        lines.append("Bu davrda zayavkalar yo'q.")
    else:
        lines.append(f"📥 Jami zayavkalar: <b>{s.total}</b>")
        lines.append(f"✅ {c['approved']} · ⏳ {c['pending']} · ❌ {c['rejected']} · 🚫 {c['cancelled']}")
        if s.approval_rate is not None:
            lines.append(f"📈 Tasdiqlash ulushi: <b>{s.approval_rate:.0f}%</b>")
        if s.avg_decide_h is not None:
            lines.append(f"⏱ O'rtacha ko'rib chiqish vaqti: <b>{_hours(s.avg_decide_h)}</b>")

        lines += ["", "💰 <b>Valyuta bo'yicha summalar</b>"]
        for cur, d in sorted(s.by_cur.items()):
            parts = [f"{STATUS[st].split()[0]} {fmt_amount(d[st])}" for st in STATUS_ORDER[:3] if d.get(st)]
            lines.append(f"<b>{cur}</b>: " + " · ".join(parts or ["—"]))

        lines += ["", f"💱 <b>{BASE_CURRENCY} ekvivalentida</b>" + (f" <i>(CBU, {rate_date})</i>" if rate_date else "")]
        lines.append(f"✅ Tasdiqlangan: <b>{fmt_amount(round(s.base['approved']))}</b>")
        lines.append(f"⏳ Kutilmoqda: <b>{fmt_amount(round(s.base['pending']))}</b>")
        lines.append(f"❌ Rad etilgan: {fmt_amount(round(s.base['rejected']))}")
        if s.avg_amount:
            lines.append(f"📐 O'rtacha zayavka: {fmt_amount(round(s.avg_amount))}")
        if s.missing_rates:
            lines.append(f"<i>⚠️ Kurs topilmadi: {', '.join(sorted(s.missing_rates))} (ekvivalentga kirmadi)</i>")

        top = sorted(s.by_user.values(), key=lambda x: x[1], reverse=True)[:5]
        if top:
            lines += ["", "👥 <b>Top so'rovchilar</b>"]
            for i, (cnt, val, name) in enumerate(top, 1):
                lines.append(f"{i}. {e(short(name, 25))} — {cnt} ta, {fmt_amount(round(val))} {BASE_CURRENCY}")

        # Tanlov turidagi qo'shimcha maydonlar bo'yicha kesim (Bo'lim, Kategoriya, ...)
        for f in [f for f in await db.list_fields() if f["type"] in ("choice", "bool")][:3]:
            agg = defaultdict(lambda: [0, 0.0])
            for r in rows:
                if r["status"] == "cancelled":
                    continue
                key = r["extra"].get(str(f["id"]))
                label = ("Ha" if key else "Yo'q") if f["type"] == "bool" and key is not None else (key or "—")
                agg[label][0] += 1
                agg[label][1] += r.get("_base", 0)
            if agg:
                lines += ["", f"🧩 <b>{e(f['name'])} bo'yicha</b>"]
                for label, (cnt, val) in sorted(agg.items(), key=lambda x: x[1][1], reverse=True)[:8]:
                    lines.append(f"• {e(label)} — {cnt} ta, {fmt_amount(round(val))} {BASE_CURRENCY}")

    # Davrdan qat'i nazar — hozirgi holat
    t = today()
    overdue = await db.overdue_pending(t.isoformat())
    week = await db.requests_due_between(t.isoformat(), (t + timedelta(days=7)).isoformat())
    week_base = sum(req_base(r, rates) or 0 for r in week)
    lines += ["", "🔔 <b>Hozirgi holat</b>"]
    lines.append(f"📅 Keyingi 7 kunda kerak: <b>{len(week)}</b> ta (~{fmt_amount(round(week_base))} {BASE_CURRENCY})")
    lines.append(f"⚠️ Muddati o'tgan, hali kutilmoqda: <b>{len(overdue)}</b> ta")
    text = "\n".join(lines)
    return text[:4000]


# ---------------------------------------------------------------- grafiklar
def _fig_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def _money_axis(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_amount(round(v))))


async def charts(period: str) -> list[tuple[str, bytes]]:
    rows = await _rows(period)
    if not rows:
        return []
    rates, _ = await get_rates()
    s = Stats(rows, rates)
    out = []
    label = _period_label(period)

    # 1) Holatlar bo'yicha (soni)
    sts = [st for st in STATUS_ORDER if s.count[st]]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie([s.count[st] for st in sts], labels=[f"{STATUS[st][2:]} ({s.count[st]})" for st in sts],
           colors=[STATUS_COLORS[st] for st in sts], autopct="%1.0f%%", startangle=90,
           wedgeprops={"width": 0.45, "edgecolor": "white"})
    ax.set_title(f"Zayavkalar holati — {label}")
    out.append(("Holatlar", _fig_bytes(fig)))

    # 2) Vaqt bo'yicha dinamika (UZS ekv.)
    start, end = period_range(period)
    if not start:
        start = min(date.fromisoformat(r["created_at"][:10]) for r in rows)
        end = today()
    monthly = (end - start).days > 62
    key = (lambda d: d[:7]) if monthly else (lambda d: d[:10])
    buckets = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if "_base" in r and r["status"] in ("approved", "pending", "rejected"):
            buckets[key(r["created_at"])][r["status"]] += r["_base"]
    if buckets:
        if monthly:
            keys = sorted(buckets)
            xt = [k[5:7] + "." + k[2:4] for k in keys]
        else:
            keys = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
            xt = [k[8:10] + "." + k[5:7] for k in keys]
        fig, ax = plt.subplots(figsize=(max(6, min(14, len(keys) * 0.45)), 4.5))
        bottom = [0.0] * len(keys)
        for st in ("approved", "pending", "rejected"):
            vals = [buckets[k][st] for k in keys]
            ax.bar(xt, vals, bottom=bottom, color=STATUS_COLORS[st], label=STATUS[st][2:])
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_title(f"Summalar dinamikasi ({BASE_CURRENCY} ekv.) — {label}")
        _money_axis(ax)
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
        out.append(("Dinamika", _fig_bytes(fig)))

    # 3) Valyutalar bo'yicha (asl valyutada, tasdiqlangan)
    curs = sorted(s.by_cur)
    if len(curs) > 1:
        fig, axes = plt.subplots(1, len(curs), figsize=(3.2 * len(curs), 4))
        for ax, cur in zip(axes, curs):
            d = s.by_cur[cur]
            sts3 = ["approved", "pending", "rejected"]
            ax.bar([STATUS[x][2:] for x in sts3], [d[x] for x in sts3], color=[STATUS_COLORS[x] for x in sts3])
            ax.set_title(cur)
            _money_axis(ax)
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
        fig.suptitle(f"Valyutalar bo'yicha — {label}")
        out.append(("Valyutalar", _fig_bytes(fig)))

    # 4) Top so'rovchilar
    top = sorted(s.by_user.values(), key=lambda x: x[1], reverse=True)[:8]
    if top and any(v for _, v, _ in top):
        fig, ax = plt.subplots(figsize=(7, 0.5 * len(top) + 1.5))
        ax.barh([short(n, 20) for _, _, n in reversed(top)], [v for _, v, _ in reversed(top)], color="#4a7bd0")
        ax.set_title(f"Top so'rovchilar ({BASE_CURRENCY} ekv.)")
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_amount(round(v))))
        out.append(("Top", _fig_bytes(fig)))

    # 5) Tanlov maydonlari bo'yicha
    for f in [f for f in await db.list_fields() if f["type"] == "choice"][:3]:
        agg = defaultdict(float)
        for r in rows:
            if r["status"] in ("approved", "pending") and "_base" in r:
                agg[r["extra"].get(str(f["id"])) or "—"] += r["_base"]
        if agg:
            items = sorted(agg.items(), key=lambda x: x[1])
            fig, ax = plt.subplots(figsize=(7, 0.5 * len(items) + 1.5))
            ax.barh([short(k, 20) for k, _ in items], [v for _, v in items], color="#8e6bd0")
            ax.set_title(f"{f['name']} bo'yicha (tasdiqlangan + kutilayotgan, {BASE_CURRENCY})")
            ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_amount(round(v))))
            out.append((f["name"], _fig_bytes(fig)))
    return out


# ---------------------------------------------------------------- Excel
async def excel(period: str) -> bytes:
    rows = await _rows(period)
    rates, rate_date = await get_rates()
    fields = await db.list_fields()
    wb = Workbook()
    ws = wb.active
    ws.title = "Zayavkalar"
    headers = ["ID", "Yaratilgan", "Muallif", "Maqsad", "Summa", "Valyuta", "Kurs", "Kurs sanasi", "Kurs manbasi",
               f"{BASE_CURRENCY} ekv.",
               "Kerakli sana", "Holat", "Ko'rib chiqdi", "Qaror vaqti", "Rad sababi", "Izoh"] + [f["name"] for f in fields]
    ws.append(headers)
    for r in rows:
        base = req_base(r, rates)
        ws.append([
            r["id"], r["created_at"], r.get("author_name") or "", r["title"], r["amount"], r["currency"],
            r.get("rate"), fmt_date(r.get("rate_used_day")) if r.get("rate_used_day") else "",
            ("Qo'lda: " + (r.get("rate_set_by") or "")) if r.get("rate_manual") else (r.get("rate_source") or ""),
            round(base, 2) if base is not None else None, fmt_date(r["needed_date"]), STATUS[r["status"]][2:],
            r.get("decider_name") or "", r["decided_at"] or "", r["reject_reason"], r["comment"],
        ] + [field_plain(f, r["extra"].get(str(f["id"]))) for f in fields])
    _style(ws, money_cols=(5, 7, 10))

    ws2 = wb.create_sheet("Xulosa")
    s = Stats(rows, rates)
    ws2.append(["Davr", _period_label(period)])
    ws2.append(["Kurslar", "Har bir zayavka o'zi kiritilgan kun kursi bilan (Zayavkalar varag'ida)"])
    ws2.append([])
    ws2.append(["Valyuta"] + [STATUS[st][2:] for st in STATUS_ORDER])
    for cur, d in sorted(s.by_cur.items()):
        ws2.append([cur] + [d.get(st, 0) for st in STATUS_ORDER])
    ws2.append([f"{BASE_CURRENCY} ekv."] + [round(s.base.get(st, 0), 2) for st in STATUS_ORDER])
    ws2.append(["Soni"] + [s.count.get(st, 0) for st in STATUS_ORDER])
    for col in range(1, 6):
        ws2.column_dimensions[get_column_letter(col)].width = 20
    for row in ws2.iter_rows(min_row=4, max_row=4):
        for cell in row:
            cell.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _style(ws, money_cols=()):
    head_fill = PatternFill("solid", fgColor="305496")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        width = max((len(str(c.value)) for c in ws[letter] if c.value is not None), default=8)
        ws.column_dimensions[letter].width = min(max(10, width + 2), 45)
        if col in money_cols:
            for c in ws[letter][1:]:
                c.number_format = "#,##0.00"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


# ---------------------------------------------------------------- qisqa hisobot
async def short_report() -> str:
    rates, _ = await get_rates()
    t = today()
    today_rows = await db.requests_created_between(t.isoformat(), t.isoformat())
    month_rows = await db.requests_created_between(t.replace(day=1).isoformat(), t.isoformat())
    st, sm = Stats(today_rows, rates), Stats(month_rows, rates)
    pending = await db.all_pending()
    pend_base = sum(req_base(r, rates) or 0 for r in pending)
    overdue = [r for r in pending if r["needed_date"] < t.isoformat()]
    soon = await db.requests_due_between(t.isoformat(), (t + timedelta(days=1)).isoformat())

    lines = [f"📝 <b>Qisqa hisobot — {t.strftime('%d.%m.%Y')}</b>", ""]
    lines.append(f"<b>Bugun:</b> {st.total} ta yangi · ✅ {st.count['approved']} · ❌ {st.count['rejected']}"
                 f" · so'ralgan ~{fmt_amount(round(sum(st.base.values()) - st.base['cancelled']))} {BASE_CURRENCY}")
    lines.append(f"<b>Shu oy:</b> {sm.total} ta · ✅ tasdiqlangan ~{fmt_amount(round(sm.base['approved']))} {BASE_CURRENCY}")
    lines.append(f"<b>⏳ Hozir kutilmoqda:</b> {len(pending)} ta (~{fmt_amount(round(pend_base))} {BASE_CURRENCY})")
    if overdue:
        lines += ["", f"⚠️ <b>Muddati o'tgan ({len(overdue)}):</b>"]
        lines += [f"  {fmt_date(r['needed_date'])} · {text_line(r)}" for r in overdue[:10]]
    if soon:
        lines += ["", "📅 <b>Bugun / ertaga kerak:</b>"]
        lines += [f"  {fmt_date(r['needed_date'])} · {text_line(r)}" for r in soon[:15]]
    return "\n".join(lines)[:4000]


# ---------------------------------------------------------------- Mini App uchun JSON
async def dashboard_data(period: str) -> dict:
    if period not in PERIODS:
        period = "month"
    rows = await _rows(period)
    rates, rate_date = await get_rates()
    s = Stats(rows, rates)
    start, end = period_range(period)
    if not start and rows:
        start = min(date.fromisoformat(r["created_at"][:10]) for r in rows)
        end = today()
    series = []
    if start:
        monthly = (end - start).days > 62
        key = (lambda d: d[:7]) if monthly else (lambda d: d[:10])
        buckets = defaultdict(lambda: defaultdict(float))
        for r in rows:
            if "_base" in r:
                buckets[key(r["created_at"])][r["status"]] += r["_base"]
        if monthly:
            keys, k = [], start.replace(day=1)
            while k <= end:
                keys.append(k.isoformat()[:7])
                k = (k.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            keys = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
        series = [{"key": k, **{st: round(buckets[k][st], 2) for st in STATUS_ORDER}} for k in keys]

    breakdowns = []
    for f in [f for f in await db.list_fields() if f["type"] in ("choice", "bool")][:4]:
        agg = defaultdict(lambda: [0, 0.0])
        for r in rows:
            if r["status"] == "cancelled":
                continue
            v = r["extra"].get(str(f["id"]))
            label = (("yes" if v else "no") if v is not None else None) if f["type"] == "bool" else v
            agg[label or "—"][0] += 1
            agg[label or "—"][1] += r.get("_base", 0)
        if agg:
            breakdowns.append({"field": f["name"], "type": f["type"], "items": [
                {"label": k, "count": c, "amount": round(v, 2)}
                for k, (c, v) in sorted(agg.items(), key=lambda x: x[1][1], reverse=True)]})

    t = today()
    overdue = await db.overdue_pending(t.isoformat())
    week = await db.requests_due_between(t.isoformat(), (t + timedelta(days=7)).isoformat())
    top = sorted(s.by_user.values(), key=lambda x: x[1], reverse=True)[:6]
    return {
        "period": period,
        "from": start.isoformat() if start else None,
        "to": end.isoformat() if end else None,
        "base": BASE_CURRENCY,
        "rate_date": rate_date,
        "total": s.total,
        "count": {st: s.count.get(st, 0) for st in STATUS_ORDER},
        "base_sum": {st: round(s.base.get(st, 0), 2) for st in STATUS_ORDER},
        "by_currency": [{"code": c, **{st: round(d.get(st, 0), 2) for st in STATUS_ORDER}} for c, d in sorted(s.by_cur.items())],
        "approval_rate": s.approval_rate,
        "avg_decide_hours": s.avg_decide_h,
        "avg_amount": s.avg_amount,
        "missing_rates": sorted(s.missing_rates),
        "top": [{"name": n, "count": c, "amount": round(v, 2)} for c, v, n in top],
        "series": series,
        "breakdowns": breakdowns,
        "upcoming_count": len(week),
        "upcoming_sum": round(sum(req_base(r, rates) or 0 for r in week), 2),
        "overdue_count": len(overdue),
    }
