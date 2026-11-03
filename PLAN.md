# Reja

## ✅ Bajarildi: 🟢 Kim onlayn (commit d4068ee)

## 💵 Pul berish: to'liq, qisman, ortiqcha, qaytarish, tejash, xato tuzatish

### Asosiy g'oya
Zayavka **tasdiqlangandan** keyin unga **pul harakatlari** yoziladi. Har bir harakat alohida qator:
summa, sana, izoh, kim kiritgan. Hech narsa o'chirilmaydi, faqat **bekor qilinadi**. Shuning uchun tarix doim to'liq qoladi.

| Harakat | Ma'nosi | Hisobga ta'siri |
|---|---|---|
| 💸 **Berildi** | Kassadan xodimga pul berildi (to'liq yoki qisman) | + |
| ↩️ **Qaytarildi** | Xodim pulni qaytardi: ortib qoldi, arzonroq topdi yoki ortiqcha berilgan edi | − |
| 🧾 **Haqiqiy xarajat** | Aslida qancha ketgani (masalan, 1 000 000 so'rab, 850 000 ga oldi) | qancha kerakligini o'zgartiradi |

### Hisob-kitob
- **So'ralgan** (S): zayavka summasi.
- **Kerak** (K): haqiqiy xarajat kiritilgan bo'lsa o'sha, bo'lmasa S.
- **Berildi (sof)** (B): berilganlar yig'indisi minus qaytarilganlar.
- **Farq** = B − K:
  - **< 0:** **Qoldiq**, yana berish kerak.
  - **= 0:** hisob yopiq.
  - **> 0:** **Qaytarilishi kerak**, xodimda ortiqcha pul bor.
- **Tejaldi** = S − K. Arzonroq topilganda chiqadi va dashboardda ko'rinadi.

### Holatlar (zayavka kartasida va ro'yxatda belgi)
| Belgi | Qachon |
|---|---|
| ⚪ To'lanmagan | Hali hech narsa berilmagan |
| 🟡 Qisman | Bir qismi berilgan, qoldiq bor |
| 🟢 To'liq berildi | Berilgan pul kerakli summaga teng |
| 🟠 Ortiqcha / qaytarish kerak | Berilgan pul kerakli summadan ko'p: ortiqcha berilgan yoki arzonroq topilgan |
| ✅ Yopildi | Xodim haqiqiy xarajatni kiritgan va farq 0 bo'lgan, ya'ni hammasi hisob-kitob qilingan |

### Misollar
1. **Qisman:** 1 000 000 so'raldi. 600 000 berildi, holat 🟡 "qoldiq 400 000". Keyin yana 400 000 berildi, holat 🟢.
2. **Arzonroq topdi:** 1 000 000 berildi, xodim "haqiqiy xarajat 850 000" deb kiritdi. Holat 🟠 "qaytarish kerak 150 000". Buxgalter "qaytarildi 150 000" deb yozadi, holat ✅ "tejaldi 150 000".
3. **Ortiqcha berilgan (xato emas):** 1 000 000 o'rniga 1 100 000 berildi. Kiritishda ogohlantirish chiqadi: "so'ralgandan 100 000 ko'p, izoh majburiy". Holat 🟠 "qaytarish kerak 100 000".
4. **Xato kiritilgan:** 1 000 000 o'rniga 100 000 yozib yuborildi. O'sha qator "bekor qilish" bilan bekor qilinadi, sababi majburiy, keyin to'g'risi kiritiladi. Bekor qilingan qator ustidan chizilgan holda tarixda qoladi.

### Kim nima qila oladi
| Amal | Xodim (egasi) | Kuzatuvchi (buxgalter) | Tasdiqlovchi | Admin / Super admin |
|---|---|---|---|---|
| Berildi yozish | — | ✅ | ✅ | ✅ |
| Qaytarildi yozish | — | ✅ | ✅ | ✅ |
| Haqiqiy xarajatni kiritish | ✅ | ✅ | ✅ | ✅ |
| "Pulni oldim" tasdiqlash | ✅ | — | — | — |
| O'z yozuvini bekor qilish | — | ✅ 24 soat ichida | ✅ 24 soat ichida | ✅ har doim |

### Cheklovlar va himoya
- Pul faqat **tasdiqlangan** zayavkaga yoziladi.
- Ortiqcha berishga ruxsat bor, lekin ogohlantirish chiqadi va izoh majburiy.
- Qaytarilgan summa berilgan sof summadan oshmaydi.
- Pul harakati bor zayavkani **qayta ochib ham, bekor qilib ham bo'lmaydi**. Avval harakatlarni bekor qilish kerak.
- Tasdiqlangan zayavka summasi o'zgartirilsa, qoldiq avtomatik qayta hisoblanadi.
- Bir tugmani ikki marta bosish ikki marta yozmaydi: ketma-ket kelgan bir xil so'rov bir marta yoziladi.
- Har bir harakat va har bir bekor qilish **audit logga** tushadi: kim, qachon, nima.

### Qayerda ko'rinadi
- **Zayavka kartasi:**
  - progress chizig'i;
  - Berildi / Qoldiq yoki Qaytarish kerak / Tejaldi;
  - harakatlar tarixi;
  - tugmalar: 💸 Berish, ↩️ Qaytarildi, 🧾 Haqiqiy xarajat.
- **Ro'yxat:** holat belgisi va filtr: To'lanmagan / Qisman / To'liq / Qaytarish kerak / Yopilgan.
- **Dashboard:** "Berildi", "Qoldiq", "Qaytarilishi kerak", "Tejaldi".
- **Excel:** ustunlar Berildi, Qaytarildi, Haqiqiy xarajat, Qoldiq/Farq va To'lov holati. Alohida varaqda barcha harakatlar.
- **Bot kartochkasi:** qisqa qator, masalan "💸 600 000 / 1 000 000 · qoldiq 400 000".
- **Muddatlar sahifasi:** tasdiqlangan, lekin to'liq berilmaganlar.

### Bildirishnomalar (qo'ng'iroqcha va Telegram)
| Hodisa | Kimga |
|---|---|
| 💸 Pul berildi (to'liq yoki qisman) | Zayavka egasi |
| ↩️ Qaytarish kerak (ortiqcha yoki tejaldi) | Zayavka egasi |
| ↩️ Qaytarish qabul qilindi | Zayavka egasi |
| 🧾 Haqiqiy xarajat kiritildi | Buxgalter va adminlar |
| 🚫 Pul yozuvi bekor qilindi | Zayavka egasi va yozuvni kiritgan odam |

### Texnik qism
- Yangi jadval `payments`:
  - `id`, `request_id`, `kind` (`payout` / `refund`), `amount`, `note`, `paid_at`;
  - `created_by`, `created_at`;
  - `voided_at`, `voided_by`, `void_reason`.
- `requests` jadvaliga yangi ustunlar:
  - `actual_amount`: haqiqiy xarajat, bo'sh bo'lishi mumkin;
  - `received_ok`: egasi "oldim" deb tasdiqlagani;
  - `paid_net`: tez filtrlash uchun saqlanadigan yig'indi.
- Pul harakatining valyutasi zayavka valyutasi bilan bir xil bo'ladi.
- Ish boshlanishidan oldin server bazasining nusxasi olinadi.
- Yangi kod uchun testlar yoziladi: hisob-kitob, ruxsatlar, cheklovlar, bekor qilish.
- Hajmi: taxminan 5–7 soat.

### Sizdan javob kerak bo'lgan savollar
1. Xodimning o'zi "pulni oldim" deb tasdiqlashi kerakmi yoki bu ortiqcha?
2. Haqiqiy xarajatni kiritishda chek yoki rasm biriktirish kerakmi?
3. Pulni zayavkadan boshqa valyutada berish holati bo'ladimi? Masalan, $ da so'rab, so'mda berish.
4. Buxgalter o'z yozuvini 24 soat ichida bekor qila olsinmi yoki faqat admin bekor qilsinmi?
