import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Railway odatda POSTGRES uchun DATABASE_URL beradi (postgresql://...)
# SQLAlchemy async uchun postgresql+asyncpg:// formatiga o'giramiz.
_raw_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./course_bot.db")
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://"):
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL = _raw_db_url

# Boshlang'ich adminlar: Telegram ID larni vergul bilan ajratib .env ga yozing
# Masalan: ADMIN_IDS=123456789,987654321
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# Asosiy egasi (owner) — to'lov cheklarini tekshirish so'rovlari FAQAT shu
# Telegram ID'ga boradi (boshqa adminlarga emas). Agar .env'da OWNER_ID
# ko'rsatilmasa, ADMIN_IDS ro'yxatidagi birinchi ID avtomatik "asosiy egasi"
# deb olinadi.
_owner_env = os.getenv("OWNER_ID", "").strip()
if _owner_env.isdigit():
    OWNER_ID = int(_owner_env)
elif ADMIN_IDS:
    OWNER_ID = ADMIN_IDS[0]
else:
    OWNER_ID = 0

# Video darslar saqlanadigan xususiy (private) Telegram kanal ID'si.
# Bot shu kanalga ADMIN sifatida qo'shilgan bo'lishi shart.
# ID odatda -100 bilan boshlanadi, masalan: -1001234567890
# Kanal ID'sini olish: kanalga xabar tashlang, keyin @userinfobot yoki
# @getidsbot orqali forward qiling.
_storage_env = os.getenv("STORAGE_CHANNEL_ID", "").strip()
STORAGE_CHANNEL_ID = int(_storage_env) if _storage_env.lstrip("-").isdigit() else 0

# "💬 Yordam" bo'limida ko'rsatiladigan qo'llab-quvvatlash akkaunti.
# Masalan: SUPPORT_USERNAME=your_support_username (@ belgisisiz)
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "support").strip().lstrip("@")
