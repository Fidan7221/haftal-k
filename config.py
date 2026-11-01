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

    # Harici API ayarları (Hafta 9)
    PRICE_API_URL = os.environ.get("PRICE_API_URL", "")
    PAYMENT_API_KEY = os.environ.get("PAYMENT_API_KEY", "")
    PAYMENT_SECRET_KEY = os.environ.get("PAYMENT_SECRET_KEY", "")
    USE_MOCK_APIS = True  # Gerçek API hazır olana kadar sahte servis kullan


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False  # True yaparsanız üretilen SQL sorguları terminale yazılır


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # Testlerde form göndermeyi kolaylaştırır


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True   # Yayında çerezler yalnızca HTTPS ile gönderilir
    REMEMBER_COOKIE_SECURE = True
    # Bulut veri tabanı boşta kalınca bağlantıyı kapatabilir; her istekte bağlantı sınanır
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    # Hafta 9'da gerçek API anahtarları girilince False yapılacak. Şimdilik canlıda da
    # sahte (mock) ödeme kullanılıyor; aksi hâlde canlı sitede ödeme adımı çalışmazdı.
    USE_MOCK_APIS = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
