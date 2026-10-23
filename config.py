"""Uygulama ayarları.

Ayarlar ortama göre üç sınıfa ayrılır:
- DevelopmentConfig: Geliştirme yaparken (hata ayıklama açık)
- TestingConfig:     pytest çalışırken (bellekte geçici veri tabanı)
- ProductionConfig:  Gerçek yayında (hata ayıklama kapalı)
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# .env dosyasındaki değişkenleri ortam değişkeni olarak yükle
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Tüm ortamların ortak ayarları."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "gelistirme-icin-gecici-anahtar")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

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
    USE_MOCK_APIS = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
