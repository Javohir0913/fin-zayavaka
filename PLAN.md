# Reja (keyinroq qilinadi)

## 1. 💵 Pul berildi / qisman berildi / qoldiq

Tasdiqlangan zayavka bo'yicha pul qancha berilgani va qancha qolgani.

- **Kim kiritadi:** Kuzatuvchi (buxgalter), Tasdiqlovchi, Admin va Super admin. Zayavka egasi "pul oldim" deb o'zi ham belgilashi mumkin.
- **Bir necha to'lov:** har biri alohida yoziladi (summa, sana, izoh, kim kiritgani). Qoldiq avtomatik hisoblanadi.
- **Holatlar:** To'lanmagan · Qisman (qoldiq bilan) · To'liq berildi.
- **Cheklovlar:**
  - qoldiqdan ko'p kiritib bo'lmaydi;
  - to'lovi bor zayavkani qayta ochib bo'lmaydi;
  - summani berilgan puldan kam qilib bo'lmaydi.
- **Bekor qilish:** to'lov o'chirilmaydi, faqat bekor qilinadi (admin yoki uni kiritgan odam). Tarix va audit logda qoladi.
- **Qayerda ko'rinadi:**
  - zayavka kartasida progress (berildi / qoldiq) va to'lovlar ro'yxati;
  - ro'yxatda belgi va filtr (To'lanmagan / Qisman / To'langan / Qoldig'i bor);
  - dashboardda "Berildi" va "Qoldiq";
  - Excelda ustunlar;
  - botdagi kartochkada.
- **Bildirishnoma:** egasiga "pul berildi (qisman)" xabari, qo'ng'iroqcha va Telegram orqali.

## 2. 🟢 Kim onlayn

Ilova yoki saytda kim hozir faol ekanini ko'rsatish.

- **Qanday aniqlanadi:**
  - ilova ochiq turganda har 30 soniyada server so'rovi bor (qo'ng'iroqcha uchun);
  - shu orqali `users.last_seen` yangilanadi; botga yozganda ham yangilanadi;
  - oxirgi faollik 1–2 daqiqa ichida bo'lsa, odam onlayn hisoblanadi.
- **Ko'rinishi:**
  - Foydalanuvchilar sahifasida 🟢 belgisi yoki "15 daqiqa oldin";
  - qayerdan kirgani (Mini App / brauzer / bot);
  - "Hozir onlayn: N".
- **Kim ko'radi:** faqat admin va super admin.
- **Cheklov:** Telegram'ning o'zidagi onlayn holatini botlarga bermaydi. Faqat bizning ilovadagi faollik ko'rinadi.
- **Hajmi:** taxminan 1–2 soat.
