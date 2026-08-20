# Online Academy — Telegram bot

Python + aiogram 3 + SQLAlchemy (async), Railway'ga deploy qilishga tayyor.

## 🎨 Premium dizayn (yangilandi)

Bot matnlari mijozga taqdim etish uchun yagona uslubga keltirildi:

- Har bir muhim ekranda bir xil **sarlavha + ajratuvchi chiziq (┈┈┈)** tuzilishi
  (`utils/format.py -> DIVIDER`), pul summalari hamma joyda bir xil formatda
  (`fmt_money()` -> "299 000 so'm"), sana bir xil formatda (`fmt_date()`).
- `/start` — foydalanuvchining ismi bilan shaxsiylashtirilgan, rolga qarab
  qo'shimcha qator (admin/o'qituvchi uchun).
- Kurs sahifasi endi **modul/dars/o'quvchilar sonini** ham ko'rsatadi va
  "⬅️ Katalogga qaytish" tugmasi bilan.
- O'qituvchining **💰 Daromadim** endi ishlaydi (avval "tez orada" degan stub
  edi): `payments` jadvalidagi ✅ to'langan summalar bo'yicha jami savdo va
  50% ulush hisoblab beradi.
- **💬 Yordam** bo'limidagi qo'llab-quvvatlash username'i endi kodga
  yozilmagan — `.env`dagi `SUPPORT_USERNAME` orqali sozlanadi (pastga qarang).
- Kritik bag'lar tuzatildi: `handlers/teacher.py`da modul/dars tartibini
  o'zgartirish va preview yoqish/o'chirish tugmalari `callback.data`ni
  to'g'ridan-to'g'ri o'zgartirishga urinardi — zamonaviy aiogram/pydantic
  obyektlari **frozen** bo'lgani uchun bu har safar xatolik bilan yiqilardi.
  Endi har bir ekran alohida `_render_*_management()` funksiyasiga
  ajratilgan va hech narsa mutatsiya qilinmaydi. `handlers/admin.py`da kurs
  tasdiqlash/rad etish ham (rasm bilan yuborilgan xabarlarda `None + str`
  xatosiga qarshi) himoyalandi.

## ✅ Nima bor

**Foundation:** rol tizimi, kurslar katalogi, moderatsiya, o'qituvchi paneli
(kurs yaratish), admin dashboard.

**To'lov tizimi — "karta + admin tasdiqlaydi" modeli, bir nechta karta bilan:**

1. Admin **💳 Kartalar** bo'limida bir nechta to'lov kartasi qo'sha oladi
   (masalan turli banklar/o'qituvchilar uchun) — har biri nom (label), karta
   raqami, egasi bilan. Kartani ✅ faol / ⏸ faolsiz qilish va 🗑 o'chirish mumkin.
2. O'quvchi **🛒 Kursni sotib olish**ni bosadi, karta tanlaydi, chek
   skrinshotini yuboradi → bot **faqat asosiy egaga** (`OWNER_ID`) chek
   rasmini ✅/❌ tugmalari bilan yuboradi.
3. ✅ Tasdiqlansa → kurs avtomatik ochiladi (Enrollment yaratiladi), o'quvchiga
   xabar boradi. ❌ bo'lsa — rad etilgani haqida xabar boradi.

Xavfsizlik tamoyili: kurs FAQAT admin ✅ Tasdiqlash bosgandan keyin ochiladi
(`utils/payments.py -> approve_payment()`).

**🎥 Video darslar tizimi — "kino bot" uslubida:**

1. O'qituvchi **🎥 Dars qo'shish** tugmasini bosadi → kursini tanlaydi →
   modulni tanlaydi (yoki ➕ Yangi modul yaratadi) → dars nomini yozadi →
   video faylni yuboradi.
2. Bot "⏳ Video yuklanmoqda... [■■■■■■■■■■] 100%" progress-bar animatsiyasini
   ko'rsatadi (kino bot tajribasiga o'xshash), so'ng videoni **xususiy
   STORAGE kanalga** (`STORAGE_CHANNEL_ID`) `copy_message` orqali ko'chiradi
   va shu kanaldagi xabar ID'sini `lessons.video_message_id` ga saqlaydi.
3. **Video hech qachon o'quvchiga to'g'ridan-to'g'ri fayl yoki link sifatida
   berilmaydi** — faqat kanaldan bevosita `copy_message` orqali nusxa
   yuboriladi (hujjatning 14-bo'limi — "Video protection" tamoyiliga mos).
4. O'quvchi **🎓 Mening kurslarim → kursni tanlaydi** → darslar ro'yxatini
   ✅/▶️/🔒 belgilar bilan ko'radi (ketma-ket ochilish: faqat tugallangan
   yoki navbatdagi dars ochiq, qolgani qulflangan).
5. O'quvchi ▶️ darsni bosganda video yuboriladi. **Video ochilishi bilan
   emas, balki o'quvchi "✅ Darsni ko'rib bo'ldim" tugmasini bosgandagina**
   dars "tugallangan" deb belgilanadi (`progress` jadvali) — bu ilgarigi
   "ochdi = tugatdi" usuliga qaraganda haqiqatga yaqinroq. Tasdiqlangach
   darhol "▶️ Keyingi dars" tugmasi bilan davom etish mumkin. Qayta
   ko'rilganda (allaqachon tugallangan darsda) tasdiqlash so'ralmaydi.
   **📊 Progressim** bo'limida har bir kurs uchun foiz + progress-bar.
6. O'qituvchining **📚 Kurslarim** ro'yxatida endi har bir kurs qancha
   dars borligini ham ko'rsatadi.

**✏️ Darsni/modulni tahrirlash — endi qo'shildi:**

1. **📚 Kurslarim** ro'yxatida har bir kurs ostida **"📂 Boshqarish"** tugmasi
   bor → modullar ro'yxati ochiladi.
2. Modulni tanlasangiz: **✏️ Modul nomi** (nomini o'zgartirish), **🗑 Modulni
   o'chirish** (tasdiqlash so'raladi — o'chirilsa, ichidagi barcha darslar
   ham birga o'chadi), va shu moduldagi darslar ro'yxati ko'rinadi.
3. Darsni tanlasangiz: **✏️ Nomini o'zgartirish**, **🎥 Videoni almashtirish**
   (eski video o'rniga yangisini yuklash — yana progress-bar bilan, storage
   kanalga yangi nusxa saqlanadi), **🗑 O'chirish**.
4. Hammasi ruxsat tekshiruvi bilan — faqat kursning egasi (yoki admin)
   tahrirlashi/o'chirishi mumkin.

**↕️ Modul/darslar tartibini qayta joylashtirish — endi qo'shildi:**

1. **📂 Boshqarish** ekranida har bir modul qatorida **⬆️/⬇️** tugmalari
   chiqadi — bosilganda modul qo'shni modul bilan o'rin almashadi
   (birinchi modulda ⬆️, oxirgisida ⬇️ ko'rinmaydi).
2. Modul ichidagi darslar ro'yxatida ham xuddi shunday **⬆️/⬇️** bor —
   dars qo'shni dars bilan o'rin almashadi.
3. Tartib `order_index` ustunida saqlanadi (`utils/ordering.py ->
   move_item()`) — shu tartib **kurs sahifasida ("📖 Kurs dasturi"), o'quvchi
   darslar ro'yxatida VA ketma-ket ochilish/progress hisobida** ishlatiladi.
   Ya'ni tartibni o'zgartirsangiz, o'quvchi ham darslarni aynan shu yangi
   tartibda ko'radi va ochadi.

**🎁 Preview dars (bepul sinov darsi) — endi qo'shildi:**

1. O'qituvchi istalgan darsni **🎁 Bepul preview qilish** tugmasi orqali
   belgilaydi (dars boshqaruv sahifasida).
2. Kurs sahifasida (hali sotib olmagan foydalanuvchiga ham) endi
   **"🎁 Bepul: {dars nomi}"** tugmasi ko'rinadi — bosilsa, enrollment/to'lov
   shart emas, video darhol yuboriladi. Bu orqali o'quvchi sotib olishdan
   oldin kurs sifatini ko'rib ko'rishi mumkin (konversiyani oshiradi).
3. Preview darsni ko'rish progressga ta'sir qilmaydi (chunki hali kursga
   yozilmagan) — faqat sotib olib, "🎓 Mening kurslarim" orqali ko'rilgan
   darslar progress hisoblanadi.

## 🟡 Video tizimi bo'yicha eslatmalar

> **Video-progress haqida aniqlik:** Telegram Bot API videoni necha foiz
> tomosha qilingani haqida hech qanday signal bermaydi (bu Bot API'ning
> texnik cheklovi — faqat to'liq Telegram mijoz ilovalari player
> statistikasiga ega). Shu sababli eng yaqin va halol yechim sifatida
> "✅ Darsni ko'rib bo'ldim" — o'quvchining o'zi tasdiqlaydigan tugma
> qo'llanildi (yuqoridagi bo'limga qarang).

> **Fayl hajmi haqida aniqlik:** video yuklash `copy_message` orqali
> ishlaydi — bot faylni o'zi yuklab olmaydi/qayta yubormaydi, faqat
> Telegram serverlariga "xabarni ko'chir" deb buyruq beradi. Fayl
> allaqachon foydalanuvchi qurilmasidan bevosita Telegram serverlariga
> yuklangan bo'ladi. Shuning uchun oddiy foydalanuvchi uchun ~2GB,
> Telegram Premium uchun ~4GB gacha video muammosiz ishlaydi — xuddi
> kino botlar ishlagani kabi.

**🏆 Sertifikat tizimi:**

1. O'quvchi biror kursning **barcha darslarini** tugatib, progress **100%**
   bo'lgan zahoti (`confirm_lesson_completed` handler ichida) tizim
   **avtomatik** — hech kim tugma bosmasdan — sertifikat yaratadi
   (`utils/certificates.py -> issue_certificate_if_completed()`).
2. Sertifikat bitta (student, course) juftligiga faqat **bir marta**
   beriladi — idempotent (qayta 100%'ga "tegib o'tilsa" ham yangisi
   yaratilmaydi, eskisi qaytariladi).
3. Har bir sertifikatga noyob tekshirish kodi beriladi, masalan
   `CB-7F3K9QZP2X` (`database.models.Certificate.code`).
4. PDF (A4, landscape, oltin ramka bilan chiroyli dizayn) `reportlab`
   yordamida **to'g'ridan-to'g'ri xotirada** generatsiya qilinadi (diskka
   fayl yozilmaydi) va o'quvchiga Telegram hujjat sifatida yuboriladi —
   ism, kurs nomi, o'qituvchi, sana va tasdiqlash kodi bilan.
5. O'quvchi **🏆 Sertifikatlarim** menyusidan barcha olingan
   sertifikatlarini istagan payt qayta yuklab olishi mumkin.
6. **👤 Profil**da endi "🏆 Sertifikatlari: N ta" ham ko'rsatiladi
   (hujjatdagi profil namunasiga mos).

> Eslatma: sertifikat faqat **progress 100%**ga asoslanadi (test/imtihon
> tizimi hali yo'q — hujjatdagi "testlar/natijalar" alohida, keyingi qadam,
> pastdagi ro'yxatga qarang).

**↕️ Modul/darslar tartibini qayta joylashtirish:**

1. **📂 Boshqarish** ekranida har bir modul/dars qatorida **⬆️/⬇️**
   tugmalari bor — bosilganda qo'shnisi bilan o'rin almashadi
   (`utils/ordering.py -> move_item()`).
2. Bu tartib **hamma joyda** ishlatiladi: kurs sahifasi, o'quvchi darslar
   ro'yxati, ketma-ket ochilish va progress hisobi.

## ❌ Umuman hali qilinmagan

Hujjatdagi reja bo'yicha hali qo'shilmagan qismlar:

1. **50/50 moliyaviy hisob-kitob va pul yechish** — `Payment` jadvalida
   `teacher_share`/`academy_share` ustunlari yo'q (hozirgi to'lov "karta +
   admin tasdiqlaydi" modeli, avtomatik bo'lish yo'q); `teacher_balances`,
   `withdrawals` jadvallari yo'q; o'qituvchining **💰 Daromadim**, **📊
   Statistika**, **💳 Pul yechish** bo'limlari hali stub xabar chiqaradi.
2. **Real to'lov provayder integratsiyasi (Payme/Click)** — hozir to'lov
   "chek skrinshot + admin qo'lda tasdiqlaydi" tarzida ishlaydi; hujjatning
   4-bo'limidagi avtomatik webhook orqali ochilish yo'q.
3. **Testlar/imtihon natijalari** — sertifikat hozircha faqat progress
   100%ga asoslanadi, alohida test/quiz tizimi yo'q.
4. **Telegram Mini App** — bot hozir faqat oddiy tugmalar
   (ReplyKeyboard/InlineKeyboard) bilan ishlaydi.
5. **Referral tizimi va promokodlar** — `promocodes`, referral bonus
   jadvallari va oqimi yo'q.
6. **Avtomatik marketing** (24 soatlik "chegirma" eslatmasi, 7 kunlik
   "sizni sog'indik" xabari) — buning uchun scheduler (APScheduler/Celery)
   kerak, hozircha yo'q.
7. **Bloklash funksiyalari** — admin panelida "O'qituvchini bloklaydi",
   "O'quvchini bloklaydi" tugmalari yo'q (`User.is_blocked` ustuni bor,
   lekin uni yoqib/o'chiradigan UI yo'q).
8. **Reviews (sharh/reyting)** jadvali va UI yo'q.
9. **Kengaytirilgan admin statistika** — hujjatdagi "Bugungi tushum",
   "Oylik tushum" kabi moliyaviy dashboard hali yo'q (hozirgi dashboard
   faqat foydalanuvchi/kurs sonlarini ko'rsatadi).

## 🚀 Railway'ga deploy qilish

1. Ushbu papkani GitHub repo qilib yuklang.
2. Railway'da **New Project → Deploy from GitHub repo**.
3. **Variables**: `BOT_TOKEN`, `ADMIN_IDS`, `OWNER_ID`, `STORAGE_CHANNEL_ID`,
   `SUPPORT_USERNAME` (pastga qarang). PostgreSQL kerak bo'lsa **New →
   Database → PostgreSQL** qo'shing.
4. **Video kanalni sozlash (MUHIM, video ishlashi uchun shart):**
   - Telegramda yangi **PRIVATE kanal** oching (masalan "Course Bot Storage").
   - Botingizni o'sha kanalga **admin** qilib qo'shing.
   - Kanalga istalgan xabar yuboring, uni **@getidsbot** ga forward qiling —
     kanal ID'sini beradi (odatda `-100` bilan boshlanadi).
   - Shu ID'ni Railway Variables'ga `STORAGE_CHANNEL_ID` sifatida qo'shing.
5. Botga `/start` yozing → admin sifatida **💳 Kartalar** orqali kamida
   bitta to'lov kartasi qo'shing.

## 🖥 Lokal ishga tushirish

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # BOT_TOKEN, ADMIN_IDS, STORAGE_CHANNEL_ID ni to'ldiring
python main.py
```

## 📁 Tuzilma

```
course_bot/
├── main.py
├── config.py                    # + STORAGE_CHANNEL_ID
├── database/
│   ├── models.py     # Lesson (video_chat_id/video_message_id), LessonProgress endi ishlatiladi
│   └── db.py
├── keyboards/common.py           # teacher menu + "🎥 Dars qo'shish"
├── handlers/
│   ├── start.py
│   ├── student.py    # katalog, to'lov, + mycourse/watch (video ko'rish, progress)
│   ├── teacher.py    # kurs yaratish + video dars yuklash FSM (kino-bot uslubi)
│   └── admin.py       # dashboard, moderatsiya, kartalar, chek tasdiqlash
├── states/teacher_states.py   # + AddLesson (module_title/lesson_title/video)
├── utils/
│   ├── roles.py
│   ├── settings.py
│   ├── payments.py
│   ├── lessons.py         # progress hisoblash, darslar tartibi, completion
│   ├── ordering.py        # YANGI: modul/dars tartibini (order_index) surish
│   └── certificates.py    # sertifikat yaratish (idempotent) + PDF chizish
├── requirements.txt
├── Procfile
├── railway.json
└── .env.example
```

## Keyingi tavsiya

Endi bot **to'liq savdo qila oladi, darslarni ko'rsatadi va kursni
tugatgan o'quvchiga sertifikat beradi** — hujjatdagi asosiy o'quvchi
tsikli (kurs tanlash → to'lash → video ko'rish → progress → sertifikat)
**to'liq yopildi**. Keyingi mantiqiy qadam — **50/50 moliyaviy hisob-kitob
va pul yechish tizimi** (o'qituvchilar daromadini ko'rishi va yechib olishi),
chunki bu o'qituvchilar uchun asosiy tsiklni yopadi.
