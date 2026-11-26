"""Uygulama ayarları.

Ayarlar ortama göre üç sınıfa ayrılır:
- DevelopmentConfig: Geliştirme yaparken (hata ayıklama açık)
- TestingConfig:     pytest çalışırken (bellekte geçici veri tabanı)
- ProductionConfig:  Gerçek yayında (hata ayıklama kapalı)
"""
import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# .env dosyasındaki değişkenleri ortam değişkeni olarak yükle
load_dotenv(os.path.join(BASE_DIR, ".env"))


DEV_SECRET_KEY = "gelistirme-icin-gecici-anahtar"


def _env_bool(name, default):
    """"1/true/evet" -> True, "0/false/hayir" -> False, boşsa varsayılan."""
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "evet", "on")


def database_url():
    """DATABASE_URL ortam değişkenini SQLAlchemy'nin anlayacağı biçime getirir (Hafta 7).

    - Boşsa: yerelde instance/app.db (SQLite) kullanılır.
    - Render/Neon gibi servisler "postgres://..." veya "postgresql://..." verir;
      SQLAlchemy'ye hangi sürücüyü (psycopg 3) kullanacağını söylemek için
      başını "postgresql+psycopg://" yaparız.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    """Tüm ortamların ortak ayarları."""

    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)

    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Oturum ve çerez güvenliği (Hafta 5)
    SESSION_COOKIE_HTTPONLY = True        # JavaScript oturum çerezini okuyamaz (XSS'e karşı)
    SESSION_COOKIE_SAMESITE = "Lax"       # Başka sitelerden gelen isteklere çerez eklenmez (CSRF'e karşı)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=7)  # "Beni hatırla" en fazla 7 gün geçerli

    # Hatalı giriş sınırı (Hafta 5): 5 hatalı denemeden sonra e-posta 5 dakika kilitlenir
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 5

    # Ürün görseli yükleme (Hafta 6)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Sayfalama
    ITEMS_PER_PAGE = 12

    # --- Harici API ayarları (Hafta 9) ---
    # Anahtarlar KODA YAZILMAZ: yalnızca ortam değişkeninden (.env / Render paneli) okunur.
    # USE_MOCK_APIS=1 (varsayılan): sahte servisler kullanılır, internet ve anahtar gerekmez.
    # USE_MOCK_APIS=0: PRICE_API_URL / PAYMENT_API_URL adreslerine gerçek istek atılır.
    USE_MOCK_APIS = _env_bool("USE_MOCK_APIS", True)
    PRICE_API_URL = os.environ.get("PRICE_API_URL", "").strip()
    PRICE_API_KEY = os.environ.get("PRICE_API_KEY", "").strip()
    PAYMENT_API_URL = os.environ.get("PAYMENT_API_URL", "").strip()
    PAYMENT_API_KEY = os.environ.get("PAYMENT_API_KEY", "").strip()
    PAYMENT_SECRET_KEY = os.environ.get("PAYMENT_SECRET_KEY", "").strip()
    # Zaman aşımı (saniye): karşı sunucu bu sürede yanıt vermezse istek kesilir
    PRICE_API_TIMEOUT = 5
    PAYMENT_API_TIMEOUT = 10
    API_MAX_RETRIES = 2              # 429 / 5xx / zaman aşımında en fazla 2 kez daha dene
    PRICE_API_MIN_INTERVAL = 0.5     # Hız sınırı: iki fiyat isteği arasında en az 0,5 sn bekle
    PRICE_SYNC_COOLDOWN = 60         # Yönetici "Fiyatları güncelle"ye en sık dakikada bir basabilir

    # --- Yapay zekâ bileşeni (Hafta 10) ---
    # İki sağlayıcı desteklenir:
    #   gemini    -> Google Gemini, ÜCRETSİZ katman (anahtar: GEMINI_API_KEY, aistudio.google.com)
    #   anthropic -> Anthropic Claude, ücretli (anahtar: ANTHROPIC_API_KEY)
    # AI_PROVIDER boşsa: GEMINI_API_KEY varsa gemini, yoksa anthropic.
    # Anahtarlar yalnızca ortam değişkeninde. Anahtar yoksa bileşen kural tabanlı
    # (yapay zekâsız) öneriye düşer; uygulama yine çalışır.
    AI_PROVIDER = (os.environ.get("AI_PROVIDER", "").strip().lower()
                   or ("gemini" if os.environ.get("GEMINI_API_KEY", "").strip() else "anthropic"))
    AI_ENABLED = _env_bool("AI_ENABLED", True) and bool(os.environ.get(
        "GEMINI_API_KEY" if AI_PROVIDER == "gemini" else "ANTHROPIC_API_KEY", "").strip())
    AI_MODEL = os.environ.get("AI_MODEL", "").strip() or (
        "gemini-3.8-flash" if AI_PROVIDER == "gemini" else "claude-opus-5-5")
    AI_TIMEOUT = 30                  # saniye
    AI_MIN_POINTS = 14               # Trend için en az 14 günlük fiyat gerekir
    AI_HISTORY_DAYS = 60             # Modele gönderilen en fazla gün sayısı
    AI_LOG_PATH = os.path.join(BASE_DIR, "instance", "ai_gunlugu.jsonl")  # istem/çıktı günlüğü


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False  # True yaparsanız üretilen SQL sorguları terminale yazılır


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # Testlerde form göndermeyi kolaylaştırır
    # Testler internete ÇIKMAZ ve para/anahtar harcamaz: her zaman sahte servis
    USE_MOCK_APIS = True
    AI_ENABLED = False
    AI_PROVIDER = "anthropic"        # .env'de Gemini anahtarı olsa da testler aynı kalsın
    AI_MODEL = "claude-opus-5-5"
    AI_LOG_PATH = None
    PRICE_API_MIN_INTERVAL = 0
    PRICE_SYNC_COOLDOWN = 0


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True   # Yayında çerezler yalnızca HTTPS ile gönderilir
    REMEMBER_COOKIE_SECURE = True
    # Bulut veri tabanı boşta kalınca bağlantıyı kapatabilir; her istekte bağlantı sınanır
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
