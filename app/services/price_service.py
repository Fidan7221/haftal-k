"""Hal fiyatı senkronizasyonu ve sorguları (Hafta 9).

sync_prices(): Harici fiyat API'sinden son N günün fiyatlarını çeker, market_prices
tablosuna yazar (varsa günceller). Yapay zekâ bileşeni (Hafta 10) bu tabloyu kullanır.

Hız sınırı (rate limit) için önlemler:
  1) Veri tabanında ZATEN olan günler tekrar istenmez (önbellek gibi). force=True hariç.
  2) İki istek arasında PRICE_API_MIN_INTERVAL kadar beklenir.
  3) Yönetici düğmesi en sık PRICE_SYNC_COOLDOWN saniyede bir çalışır.
  4) Sunucu yine de 429 dönerse http.py bekleyip yeniden dener; olmazsa işlem DURUR
     (zorlamaya devam etmek anahtarın engellenmesine yol açar).

Bir günün isteği başarısız olursa o gün atlanır, diğerleri kaydedilir; sonuç raporunda yazar.
Kimlik doğrulama veya hız sınırı hatasında döngü hemen durur (diğer günler de başarısız olur).
"""
import logging
import time
from datetime import date, timedelta

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.integrations import http
from app.integrations.http import ApiAuthError, ApiRateLimitError, IntegrationError
from app.integrations.price_api import MOCK_SOURCE, get_price_client
from app.models import Category, MarketPrice

log = logging.getLogger(__name__)

_last_manual_sync = 0.0  # yönetici düğmesi için son çalışma zamanı (time.monotonic)

_TR = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def normalize(text):
    """'Köy Tereyağı' -> 'koy tereyagi' (Türkçe karakterleri sadeleştirip küçültür)."""
    text = (text or "").replace("İ", "i").replace("I", "ı").lower()
    return " ".join(text.translate(_TR).split())


def _category_map():
    return {normalize(c.name): c.id for c in Category.query.all()}


def sync_prices(days=30, today=None, force=False):
    """Son `days` günün fiyatlarını çeker. Dönüş: rapor sözlüğü."""
    config = current_app.config
    client = get_price_client(config)
    today = today or date.today()
    report = {"source": client.source, "days": 0, "inserted": 0, "updated": 0,
              "skipped_rows": 0, "cached_days": 0, "errors": []}

    existing_days = set()
    if not force:
        existing_days = {d for (d,) in db.session.query(MarketPrice.price_date)
                         .filter(MarketPrice.source == client.source).distinct()}
    categories = _category_map()
    interval = config.get("PRICE_API_MIN_INTERVAL", 0)

    for offset in range(days - 1, -1, -1):  # eskiden yeniye
        day = today - timedelta(days=offset)
        if day in existing_days:
            report["cached_days"] += 1
            continue
        if report["days"] and interval:
            http.sleep(interval)  # hız sınırına saygı
        try:
            quotes, skipped = client.fetch_day(day)
        except (ApiAuthError, ApiRateLimitError) as error:
            report["errors"].append(f"{day:%d.%m.%Y}: {error.user_message}")
            log.error("Fiyat senkronizasyonu durduruldu: %s", error.detail)
            break
        except IntegrationError as error:
            report["errors"].append(f"{day:%d.%m.%Y}: {error.user_message}")
            continue

        report["days"] += 1
        report["skipped_rows"] += skipped
        for quote in quotes:
            _upsert(quote, client.source, categories, report)
        db.session.commit()  # gün gün kaydet: yarıda kesilse bile alınan günler kalır

    return report


def _upsert(quote, source, categories, report):
    row = MarketPrice.query.filter_by(product_name=quote.product_name, source=source,
                                      price_date=quote.price_date).first()
    if row is None:
        row = MarketPrice(product_name=quote.product_name, source=source, price_date=quote.price_date)
        db.session.add(row)
        report["inserted"] += 1
    else:
        report["updated"] += 1
    row.unit = quote.unit
    row.min_price = quote.min_price
    row.max_price = quote.max_price
    row.avg_price = quote.avg_price
    row.category_id = categories.get(normalize(quote.product_name))


def manual_sync_allowed():
    """Yönetici düğmesi için basit hız sınırı. Dönüş: (izin var mı, kalan saniye)."""
    cooldown = current_app.config.get("PRICE_SYNC_COOLDOWN", 60)
    remaining = cooldown - (time.monotonic() - _last_manual_sync)
    return remaining <= 0, max(0, int(remaining))


def mark_manual_sync():
    global _last_manual_sync
    _last_manual_sync = time.monotonic()


# --- Sorgular ---------------------------------------------------------------------------

def latest_prices():
    """Her ürünün en son fiyatı + 7 gün önceye göre değişim yüzdesi."""
    latest_day = db.session.query(func.max(MarketPrice.price_date)).scalar()
    if latest_day is None:
        return None, []
    week_ago = {r.product_name: r.avg_price for r in
                MarketPrice.query.filter_by(price_date=latest_day - timedelta(days=7))}
    rows = []
    for row in MarketPrice.query.filter_by(price_date=latest_day).order_by(MarketPrice.product_name):
        old = week_ago.get(row.product_name)
        change = float((row.avg_price - old) / old * 100) if old else None
        rows.append({"row": row, "change_pct": change})
    return latest_day, rows


def is_sample_data():
    return MarketPrice.query.filter(MarketPrice.source != MOCK_SOURCE).first() is None


def market_names():
    return [name for (name,) in db.session.query(MarketPrice.product_name).distinct()]


def match_market_name(product):
    """Üreticinin ürününü hal fiyat listesindeki bir ürünle eşleştirir.

    'Salkım Domates' -> 'Domates', 'Köy Tereyağı' -> 'Tereyağı', 'Çiçek Balı' -> 'Bal'.
    Önce ürün adında, sonra kategori adında aranır; birden fazla eşleşmede en uzun ad seçilir.
    """
    names = market_names()
    for text in (product.name, product.category.name if product.category else ""):
        words = normalize(text).split()
        # Kelime BAŞI eşleşmeli: "bal" -> "balı" evet, ama "balkabağı" içindeki "bal" de olur;
        # bu yüzden ek yalnızca 1-2 harf olabilir (Türkçe iyelik eki: -ı, -sı, -i ...)
        hits = [name for name in names
                if any(w.startswith(normalize(name)) and len(w) - len(normalize(name)) <= 2
                       for w in words)]
        if hits:
            return max(hits, key=len)
    return None


def price_series(market_name, days=60):
    """[(tarih, ortalama fiyat), ...] eskiden yeniye. Aynı gün birden çok kaynak varsa ortalama alınır."""
    rows = (db.session.query(MarketPrice.price_date, func.avg(MarketPrice.avg_price))
            .filter(MarketPrice.product_name == market_name)
            .group_by(MarketPrice.price_date)
            .order_by(MarketPrice.price_date.desc())
            .limit(days).all())
    return [(day, float(avg)) for day, avg in reversed(rows)]


def unit_of(market_name):
    row = MarketPrice.query.filter_by(product_name=market_name).order_by(MarketPrice.price_date.desc()).first()
    return row.unit if row else "kg"
