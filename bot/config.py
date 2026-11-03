import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Super admin — FAQAT BITTA: ADMIN_IDS dagi birinchi Telegram ID.
# (Qolgan ID lar e'tiborsiz qoldiriladi; adminlarni super admin bot/ilova orqali tayinlaydi.)
_ADMIN_LIST = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()]
SUPERADMIN_ID: int | None = _ADMIN_LIST[0] if _ADMIN_LIST else None
EXTRA_ADMIN_IDS = _ADMIN_LIST[1:]
ADMIN_IDS = {SUPERADMIN_ID} if SUPERADMIN_ID else set()

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "expenses.db"))
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

# Har kuni shu soatda qisqa hisobot yuboriladi (0-23). -1 = o'chirilgan
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))

# Birinchi ishga tushishda qo'shiladigan valyutalar
DEFAULT_CURRENCIES = [c.strip().upper() for c in os.getenv("CURRENCIES", "UZS,USD,EUR,RUB").split(",") if c.strip()]

# Analitika uchun asosiy valyuta (kurslar CBU dan olinadi, shuning uchun UZS)
BASE_CURRENCY = "UZS"
CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

PAGE_SIZE = 8

# Mini App (Telegram WebApp)
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
# Tashqaridan ochiladigan HTTPS manzil (masalan, https://xxx.trycloudflare.com). Bo'sh bo'lsa — tugma chiqmaydi
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
