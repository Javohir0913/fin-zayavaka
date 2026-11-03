# 💸 Xarajat zayavkalari boti (Zayavka na rasxod)

Xodimlar yangi xarajat uchun pul so'raydi (har xil valyutada), tasdiqlovchilar ✅ tasdiqlaydi / ❌ rad etadi,
buxgalter va rahbariyat dashboard, grafik va Excel orqali analitika ko'radi.

## Imkoniyatlar

| | |
|---|---|
| **Zayavka** | Maqsad, summa, valyuta (UZS/USD/EUR/RUB/…), **qaysi kunga kerak**, izoh + admin qo'shgan maydonlar |
| **Holatlar** | ⏳ Kutilmoqda · ✅ Tasdiqlangan · ❌ Rad etilgan (sabab bilan) · 🚫 Bekor qilingan |
| **Ko'rish / o'zgartirish** | Ro'yxatlar (filtr, sahifalash), kartochka, tahrirlash, tarix (kim, qachon, nima o'zgartirdi), `/r12` buyrug'i |
| **Dostup (rollar)** | 👤 Xodim · 🛡 Tasdiqlovchi · 👁 Kuzatuvchi/buxgalter · 👑 Admin · ⛔ Bloklangan |
| **Qo'shimcha maydonlar** | Admin o'zi qo'shadi: 📝 matn, 🔢 raqam, 📅 sana, 🔘 tanlov ro'yxati, ☑️ ha/yo'q, 📎 fayl/rasm (chek). Majburiy/ixtiyoriy, yoqish/o'chirish, tartib |
| **Muddatlar** | Keyingi 14 kunda kerak bo'ladigan zayavkalar kunlar bo'yicha + muddati o'tganlar |
| **Dashboard** | Davr: bugun / hafta / oy / o'tgan oy / yil / hammasi. Soni, summalar valyuta bo'yicha, **UZS ekvivalenti (CBU kursi)**, tasdiqlash %, o'rtacha ko'rib chiqish vaqti, top so'rovchilar, "Bo'lim"/"Kategoriya" kabi maydonlar kesimi |
| **Grafiklar** | Holatlar, dinamika, valyutalar, top so'rovchilar, tanlov maydonlari bo'yicha |
| **Excel** | Barcha zayavkalar + qo'shimcha maydonlar + xulosa varag'i |
| **Qisqa hisobot** | Tugma orqali va har kuni soat 9:00 da avtomatik |
| **Bildirishnomalar** | Yangi zayavka → tasdiqlovchilarga (tugmalar bilan); qaror/tahrir → muallifga; yangi foydalanuvchi → adminga |

### Kim nima qila oladi

| Amal | Xodim | Tasdiqlovchi | Kuzatuvchi | Admin |
|---|:-:|:-:|:-:|:-:|
| Zayavka yaratish, o'zinikini ko'rish | ✅ | ✅ | ✅ | ✅ |
| O'z kutilayotgan zayavkasini tahrirlash/bekor qilish | ✅ | ✅ | ✅ | ✅ |
| Barcha zayavkalarni ko'rish | | ✅ | ✅ | ✅ |
| Tasdiqlash / rad etish | | ✅ | | ✅ |
| Dashboard, grafik, Excel, hisobot | | ✅ | ✅ | ✅ |
| Istalgan zayavkani tahrirlash, kutishga qaytarish | | | | ✅ |
| Rollar, maydonlar, valyutalar | | | | ✅ |

## O'rnatish

```bash
cd expense_bot
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env      # Linux: cp .env.example .env
```

`.env` faylida `BOT_TOKEN` (@BotFather) va `ADMIN_IDS` (o'z Telegram ID ingiz) ni yozing.

```bash
python -m bot
```

## Birinchi qadamlar

1. Admin botga `/start` yozadi → menyuda **⚙️ Admin panel** chiqadi.
2. **🧩 Qo'shimcha maydonlar → ➕** — masalan: `Bo'lim` (tanlov: Marketing, IT, Ofis), `Chek rasmi` (fayl), `Loyiha` (matn).
3. Xodimlar botga `/start` yozadi → adminga xabar keladi → bitta tugma bilan rol beriladi.
4. Xodim **➕ Yangi zayavka** → tasdiqlovchilarga bildirishnoma ✅/❌ tugmalari bilan keladi.

## Tuzilma

```
bot/
  __main__.py      ishga tushirish
  config.py        .env sozlamalari
  db.py            SQLite (users, requests, fields, currencies, history)
  middlewares.py   ro'yxatdan o'tkazish va dostup
  fieldinput.py    qo'shimcha maydonlarni so'rash/tekshirish
  render.py        kartochkalar
  reports.py       dashboard, grafiklar, Excel, qisqa hisobot
  rates.py         CBU valyuta kurslari
  scheduler.py     kunlik hisobot
  handlers/        common, create, view, admin, analytics
```

Ma'lumotlar `data/expenses.db` da saqlanadi — zaxira nusxa uchun shu faylni nusxalash kifoya.
Serverda doimiy ishlashi uchun `systemd` yoki `pm2`/`supervisor` orqali `python -m bot` ni ishga tushiring.

## 📱 Mini App (Telegram WebApp)

Bot bilan bitta jarayonda `http://127.0.0.1:8080` da ishlaydi: zamonaviy dizayn, **dark/light/avto** mavzu,
**o'zbek / rus / ingliz** tillari. Ichida: dashboard va grafiklar, zayavkalar ro'yxati (qidiruv, filtrlar),
batafsil kartochka (tasdiqlash/rad etish, tarix, fayllar), yaratish/tahrirlash formasi (barcha qo'shimcha maydonlar,
fayl yuklash), muddatlar, admin panel (rollar, maydonlar, valyutalar).

Telegram faqat **HTTPS** manzilni ochadi. Lokal sinov uchun:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

Chiqqan `https://....trycloudflare.com` manzilni `.env` dagi `WEBAPP_URL=` ga yozing va botni qayta ishga tushiring.
Shundan so'ng menyuda **📱 Ilovani ochish** tugmasi va chat pastidagi **Ilova** tugmasi paydo bo'ladi.
Doimiy ishlatish uchun serverda o'z domeningiz + nginx (HTTPS) orqali `WEB_PORT` ga proksi qiling.

Xavfsizlik: har bir API so'rovi Telegram `initData` imzosi (bot tokeni bilan HMAC) orqali tekshiriladi, 24 soatdan eski imzo rad etiladi.

## 🚀 Server (production)

| | |
|---|---|
| Manzil | https://fin.coffee-nap.uz |
| Papka | `/home/azureuser/fin-zayavka` |
| Servis | `systemd` → `fin-zayavka` (port 8095, nginx orqali HTTPS) |
| Zaxira | har kuni 03:15 (UTC) → `~/backups/fin-zayavka/`, 14 kun saqlanadi |

```bash
# Yangilash (lokalda push qilgandan keyin):
ssh azureuser@SERVER 'bash ~/fin-zayavka/deploy/update.sh'

# Loglar va holat:
ssh azureuser@SERVER 'journalctl -u fin-zayavka -f'
ssh azureuser@SERVER 'sudo systemctl restart fin-zayavka'
```

⚠️ Bitta bot tokeni bilan faqat **bitta** nusxa ishlashi mumkin: server ishlayotganda botni lokal kompyuterda ishga tushirmang
(yoki lokal sinov uchun alohida test bot tokenidan foydalaning).

## 🔐 Rollar ierarxiyasi

| Kim | Kimga qanday rol bera oladi |
|---|---|
| ⭐ **Super admin** (faqat bitta — `.env` dagi `ADMIN_IDS` ning birinchisi) | Hammaga: admin berish/olish, adminni bloklash, boshqa barcha rollar. Uning rolini hech kim o'zgartira olmaydi. |
| 👑 **Admin** | Faqat admin bo'lmaganlarga: 👤 Xodim, 🛡 Tasdiqlovchi, 👁 Kuzatuvchi, ⛔ Bloklash (yangi kelganlar ham). Admin rolini bera olmaydi; boshqa adminga, super adminga va o'ziga tega olmaydi. |

Qoida bitta joyda: `bot/utils.py → role_change_error()` — bot va Mini App bir xil ishlaydi.

## 🧾 Audit log (o'zgarishlar tarixi)

Har bir o'zgarish `audit_log` jadvaliga yoziladi: **kim, qachon, nimani, oldin → keyin**
(zayavka maydonlari, holat, rad sababi, rollar, qo'shimcha maydonlar, valyutalar, yangi foydalanuvchilar).

- **3 oy** (90 kun) dan eski yozuvlar har kuni avtomatik `deleted = 'Y'` (arxiv) bo'ladi — **bazadan o'chirilmaydi**.
- Tarixni **qo'lda o'chirish imkoniyati yo'q** — hech kim, super admin ham.
- Super admin arxivdagi (`Y`) yozuvni `N` ga tiklay oladi; tiklashning o'zi ham tarixga alohida yozuv bo'lib tushadi
  (kim, qachon, qaysi yozuvni). Tiklangan yozuv qayta avto-arxivlanmaydi.
- Ko'rish: Mini App → **Yana → O'zgarishlar tarixi** (adminlar — faol yozuvlar; super admin — arxiv ham).

## 🔎 Qidiruv

Zayavkalar va tarix qidiruvi (`bot/search.py`): katta/kichik harf farqsiz (kirillda ham), `o'` = `o‘` = `oʻ`,
`2 500 000` = `2500000`, bir nechta so'z istalgan tartibda (`ofis printer`), maqsad, izoh, muallif, username,
valyuta, summa, qo'shimcha maydon qiymatlari va rad sababi bo'yicha. `#12` — aynan 12-ID.
- Hamma o'zgarishlar `bot/services.py` orqali o'tadi, shuning uchun log hech bir yo'lda tushib qolmaydi.
