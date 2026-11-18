"""Hal fiyatı API istemcisi (Hafta 9).

İki istemci aynı arayüze sahiptir: `fetch_day(day) -> (quotes, skipped)`.
  - HalPriceClient : gerçek REST API (PRICE_API_URL). Kimlik doğrulama: "X-API-Key" başlığı.
  - MockPriceClient: internete çıkmadan, her gün için AYNI (deterministik) örnek fiyat üretir.
                     Geliştirme, test ve canlı demo için.

Beklenen gerçek API yanıtı (GET {PRICE_API_URL}/prices?date=2026-11-18):
    {
      "date": "2026-11-18",
      "items": [
        {"product": "Domates", "unit": "kg", "min": 20.0, "max": 30.0, "avg": 25.5},
        ...
      ]
    }
Farklı bir sağlayıcıya geçilirse YALNIZCA `parse_items()` değişir; servis katmanı etkilenmez.

Yanıt ayrıştırma (parse): API'ye güvenmeyiz. Her satır kontrol edilir; adı boş, fiyatı
negatif/eksik ya da min <= ort <= maks kuralını bozan satır ATLANIR ve sayılır.
"""
import math
import zlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.integrations.http import ApiResponseError, request_json

MOCK_SOURCE = "ornek_veri"
API_SOURCE = "hal_api"


@dataclass(frozen=True)
class PriceQuote:
    product_name: str
    unit: str
    min_price: Decimal
    max_price: Decimal
    avg_price: Decimal
    price_date: date


def _money(value):
    """Sayıyı iki basamaklı Decimal'e çevirir; olmazsa None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number


def parse_items(payload, day):
    """API yanıtını doğrular ve PriceQuote listesine çevirir. Dönüş: (geçerli, atlanan_sayısı)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ApiResponseError("Fiyat yanıtında 'items' listesi yok")

    quotes, skipped = [], 0
    for item in payload["items"]:
        if not isinstance(item, dict):
            skipped += 1
            continue
        name = str(item.get("product") or "").strip()[:120]
        unit = str(item.get("unit") or "kg").strip()[:10] or "kg"
        avg = _money(item.get("avg"))
        low = _money(item.get("min")) or avg
        high = _money(item.get("max")) or avg
        if not name or avg is None or not (low <= avg <= high):
            skipped += 1
            continue
        quotes.append(PriceQuote(name, unit, low, high, avg, day))
    return quotes, skipped


class HalPriceClient:
    source = API_SOURCE

    def __init__(self, base_url, api_key, timeout=5, max_retries=2, session=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session

    def fetch_day(self, day):
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key  # anahtar başlıkta gider, adreste (URL) DEĞİL
        payload = request_json("GET", f"{self.base_url}/prices", params={"date": day.isoformat()},
                               headers=headers, timeout=self.timeout,
                               max_retries=self.max_retries, session=self.session)
        return parse_items(payload, day)


# --- Sahte (mock) istemci -------------------------------------------------------------

# (ürün, birim, taban fiyat TL) — gerçekçi büyüklükte uydurma değerler
MOCK_PRODUCTS = [
    ("Domates", "kg", 25), ("Biber", "kg", 38), ("Patates", "kg", 15),
    ("Elma", "kg", 30), ("Üzüm", "kg", 45), ("Kayısı", "kg", 180),
    ("Fasulye", "kg", 85), ("Nohut", "kg", 70), ("Bal", "kg", 600),
    ("Tereyağı", "kg", 480), ("Peynir", "kg", 300),
]


def _unit_noise(name, day):
    """İsim+tarihe bağlı, her çalıştırmada AYNI çıkan -1..1 arası sayı (rastgele değil)."""
    return (zlib.crc32(f"{name}|{day.isoformat()}".encode()) % 2001) / 1000 - 1


def mock_price(name, base, day):
    """Uzun dönemli dalga (mevsim etkisi) + haftalık dalga + küçük gürültü."""
    phase = zlib.crc32(name.encode()) % 120          # her ürünün dalgası farklı yerde
    n = day.toordinal()
    seasonal = 0.15 * math.sin(2 * math.pi * (n + phase) / 120)
    weekly = 0.03 * math.sin(2 * math.pi * n / 7)
    noise = 0.02 * _unit_noise(name, day)
    return Decimal(str(base * (1 + seasonal + weekly + noise))).quantize(Decimal("0.01"))


class MockPriceClient:
    source = MOCK_SOURCE

    def fetch_day(self, day):
        items = []
        for name, unit, base in MOCK_PRODUCTS:
            avg = mock_price(name, base, day)
            items.append({"product": name, "unit": unit, "avg": float(avg),
                          "min": float(avg * Decimal("0.85")), "max": float(avg * Decimal("1.15"))})
        # Gerçek API ile AYNI doğrulamadan geçer
        return parse_items({"date": day.isoformat(), "items": items}, day)


def get_price_client(config):
    """Ayarlara göre doğru istemciyi seçer (fabrika fonksiyonu)."""
    if config.get("USE_MOCK_APIS", True) or not config.get("PRICE_API_URL"):
        return MockPriceClient()
    return HalPriceClient(config["PRICE_API_URL"], config.get("PRICE_API_KEY", ""),
                          timeout=config.get("PRICE_API_TIMEOUT", 5),
                          max_retries=config.get("API_MAX_RETRIES", 2))
