"""Fiyat trendi ve satış zamanı önerisi servisi (Hafta 10).

suggest_for_product(product):
  1) Ürünü hal fiyat listesindeki bir ürünle eşleştir     (price_service.match_market_name)
  2) Fiyat serisini hazırla (en fazla 60 gün, en az 14)    (price_service.price_series)
  3) Sayısal analiz + kural tabanlı öneri                  (ai.trend)
  4) Yapay zekâ açıksa: istem -> Claude -> JSON -> doğrulama (ai.llm_advisor)
       doğrulamadan geçerse yapay zekâ önerisi, geçmezse kural tabanlı öneri kullanılır
  5) Sonucu price_predictions tablosuna kaydet, istemi ve çıktıyı AI günlüğüne yaz

Maliyet ve hız sınırı: Aynı ürün için aynı gün içinde tekrar sorulursa kayıtlı tahmin
gösterilir (API çağrılmaz). "Yeniden hesapla" ile günde en fazla MAX_DAILY_REFRESH kez.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from flask import current_app

from app.ai import llm_advisor
from app.ai.trend import FORECAST_DAYS, Advice, analyze, rule_based_advice
from app.extensions import db
from app.models import ListingStatus, PricePrediction
from app.services import price_service
from app.services.errors import ServiceError

log = logging.getLogger(__name__)

RULE_MODEL = "kural_tabanli_v1"
MAX_DAILY_REFRESH = 5


@dataclass
class Suggestion:
    market_name: str
    unit: str
    series: list
    stats: object
    advice: Advice
    prediction: PricePrediction
    from_cache: bool = False
    notes: list = field(default_factory=list)     # neden yapay zekâ kullanılmadı vb.
    warnings: list = field(default_factory=list)  # doğrulama uyarıları
    listing_price: Decimal | None = None
    listing_diff_pct: float | None = None

    @property
    def used_ai(self):
        return self.prediction.model_name != RULE_MODEL


def ai_status():
    """Ekranda göstermek için: (açık mı, açıklama)."""
    config = current_app.config
    if config.get("AI_ENABLED"):
        return True, f"Yapay zekâ açık ({config.get('AI_MODEL')})"
    return False, ("Yapay zekâ kapalı (GEMINI_API_KEY veya ANTHROPIC_API_KEY tanımlı değil): "
                   "kural tabanlı öneri kullanılıyor.")


def _today_utc():
    return datetime.now(timezone.utc).date()


def _todays_predictions(product):
    start = datetime.combine(_today_utc(), datetime.min.time(), tzinfo=timezone.utc)
    return (PricePrediction.query.filter(PricePrediction.product_id == product.id,
                                         PricePrediction.created_at >= start)
            .order_by(PricePrediction.created_at.desc()))


def suggest_for_product(product, refresh=False):
    config = current_app.config
    market = price_service.match_market_name(product)
    if market is None:
        raise ServiceError(f"'{product.name}' için hal fiyat listesinde eşleşen ürün bulunamadı. "
                           "Öneri yalnızca hal fiyatı takip edilen ürünler için verilebilir.")
    unit = price_service.unit_of(market)
    series = price_service.price_series(market, config.get("AI_HISTORY_DAYS", 60))
    min_points = config.get("AI_MIN_POINTS", 14)
    if len(series) < min_points:
        raise ServiceError(f"'{market}' için en az {min_points} günlük fiyat gerekli, "
                           f"şu an {len(series)} gün var. Yönetici fiyatları güncellemeli.")

    stats = analyze(series)
    baseline = rule_based_advice(stats, unit)

    todays = _todays_predictions(product)
    cached = todays.first()
    if cached is not None and not refresh:
        advice = baseline if cached.model_name == RULE_MODEL else Advice(
            cached.trend, float(cached.predicted_price), cached.confidence or 0,
            cached.recommendation or "", [], source="llm")
        return _finish(product, market, unit, series, stats, advice, cached, from_cache=True)
    if refresh and todays.count() >= MAX_DAILY_REFRESH:
        raise ServiceError(f"Bu ürün için bugün en fazla {MAX_DAILY_REFRESH} kez öneri hesaplanabilir.")

    advice, model_name, notes, warnings = baseline, RULE_MODEL, [], []
    if config.get("AI_ENABLED"):
        advice, model_name, notes, warnings = _ask_ai(config, product, market, unit, series, stats, baseline)
    else:
        notes.append(ai_status()[1])

    prediction = PricePrediction(
        product=product, model_name=model_name[:50],
        predicted_price=Decimal(str(advice.predicted_price)).quantize(Decimal("0.01")),
        target_date=_today_utc() + timedelta(days=FORECAST_DAYS),
        trend=advice.trend, confidence=advice.confidence,
        recommendation=advice.recommendation[:255],
    )
    db.session.add(prediction)
    db.session.commit()
    return _finish(product, market, unit, series, stats, advice, prediction, notes=notes, warnings=warnings)


def _ask_ai(config, product, market, unit, series, stats, baseline):
    user_prompt = llm_advisor.build_prompt(market, unit, series, stats)
    entry = {"zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "urun_id": product.id, "hal_urunu": market, "istem_surumu": llm_advisor.PROMPT_VERSION,
             "model": config.get("AI_MODEL"), "istem": user_prompt}
    notes, warnings = [], []
    try:
        raw, model_used = llm_advisor.call_model(config, user_prompt)
        entry["model"] = model_used
        entry["ham_cikti"] = raw
        data = llm_advisor.parse_output(raw)
        advice, problems, warnings = llm_advisor.validate_output(data, stats)
        entry.update(sorunlar=problems, uyarilar=warnings)
    except llm_advisor.LlmError as error:
        entry["hata"] = str(error)
        advice, problems = None, [str(error)]

    if advice is None:
        # Render'ın "Logs" ekranında da görünsün (AI günlüğü dosyası her kurulumda silinir)
        log.warning("Yapay zekâ çıktısı kullanılmadı (ürün #%s, %s): %s",
                    product.id, entry.get("model"), "; ".join(problems))
        notes.append("Yapay zekâ çıktısı kullanılmadı, kural tabanlı öneri gösteriliyor: " + "; ".join(problems))
        entry["kullanilan"] = "kural_tabanli"
        _write_log(config, entry)
        return baseline, RULE_MODEL, notes, warnings

    entry["kullanilan"] = "yapay_zeka"
    _write_log(config, entry)
    return advice, entry["model"] or config.get("AI_MODEL"), notes, warnings


def _finish(product, market, unit, series, stats, advice, prediction, **extra):
    result = Suggestion(market, unit, series, stats, advice, prediction, **extra)
    # Üreticinin açık ilanı varsa fiyatını hal fiyatıyla karşılaştır (birimler aynıysa)
    listing = next((l for l in product.listings if l.status == ListingStatus.ACTIVE), None)
    if listing is not None and product.unit == unit:
        result.listing_price = listing.price
        result.listing_diff_pct = float((listing.price - Decimal(str(stats.last_price)))
                                        / Decimal(str(stats.last_price)) * 100)
    return result


def chart_points(series, width=600, height=160, pad=8):
    """Fiyat serisini SVG çizgi grafiği noktalarına çevirir ('x,y x,y ...')."""
    prices = [p for _, p in series]
    low, high = min(prices), max(prices)
    span = (high - low) or 1
    step = (width - 2 * pad) / max(len(prices) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{pad + (high - p) / span * (height - 2 * pad):.1f}"
                    for i, p in enumerate(prices))


# --- AI günlüğü (istem ve çıktı kaydı) -------------------------------------------------

def _write_log(config, entry):
    path = config.get("AI_LOG_PATH")
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:  # günlük yazılamazsa öneri yine gösterilir
        log.warning("AI günlüğü yazılamadı: %s", error)


def read_log(limit=50):
    path = current_app.config.get("AI_LOG_PATH")
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as file:
        lines = file.readlines()[-limit:]
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


# --- Fotoğraf incelemesi (v0.10.4): yapay zekâ ürün fotoğrafına bakıp öneri verir -----------

MAX_DAILY_PHOTO_REVIEWS = 5
_photo_review_counts = {}  # (ürün id, gün) -> sayı. Bellekte: sunucu yeniden başlayınca sıfırlanır.


def _photo_bytes(product):
    """Ürün fotoğrafının baytları ve türü; yoksa None."""
    from app.utils.uploads import CONTENT_TYPES, get_extension, read_product_image

    path = product.image_path
    if path and path.startswith("demo/"):  # git'teki örnek görsel (static/img/demo)
        full = os.path.join(current_app.static_folder, "img", path)
        if not os.path.isfile(full):
            return None
        with open(full, "rb") as file:
            return file.read(), CONTENT_TYPES.get(get_extension(full), "image/jpeg")
    return read_product_image(path, current_app.config["UPLOAD_FOLDER"])


def has_photo(product):
    return _photo_bytes(product) is not None


def review_product_photo(product):
    """Fotoğrafı yapay zekâya inceletir. Dönüş: (PhotoReview, uyarılar). Hata: ServiceError.

    Fiyat önerisinden farkı: kural tabanlı yedek YOK (fotoğrafı yapay zekâsız yorumlayamayız);
    sorun olursa nedeni kullanıcıya gösterilir.
    """
    from app.ai import photo_review

    config = current_app.config
    if not config.get("AI_ENABLED"):
        raise ServiceError("Fotoğraf incelemesi için yapay zekâ açık olmalı "
                           "(GEMINI_API_KEY veya ANTHROPIC_API_KEY tanımlı değil).")
    image = _photo_bytes(product)
    if image is None:
        raise ServiceError("Bu ürünün fotoğrafı yok. Önce 'Düzenle' ile bir fotoğraf yükleyin.")

    key = (product.id, _today_utc())
    if _photo_review_counts.get(key, 0) >= MAX_DAILY_PHOTO_REVIEWS:
        raise ServiceError(f"Bu ürünün fotoğrafı bugün en fazla {MAX_DAILY_PHOTO_REVIEWS} kez incelenebilir.")
    _photo_review_counts[key] = _photo_review_counts.get(key, 0) + 1

    category = product.category.name if product.category else ""
    prompt = photo_review.build_photo_prompt(product.name, category, product.unit)
    entry = {"zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tur": "fotograf",
             "urun_id": product.id, "hal_urunu": f"{product.name} (fotoğraf)",
             "istem_surumu": photo_review.PHOTO_PROMPT_VERSION, "model": config.get("AI_MODEL"),
             # Fotoğrafın kendisi günlüğe yazılmaz; yalnızca türü ve boyutu
             "istem": f"{prompt}\n\n[fotoğraf: {image[1]}, {len(image[0]) // 1024} KB]"}
    try:
        raw, model_used = llm_advisor.call_model(
            config, prompt, system=photo_review.PHOTO_SYSTEM_PROMPT, schema=photo_review.PHOTO_SCHEMA,
            gemini_schema=photo_review.PHOTO_GEMINI_SCHEMA, image=image)
        entry.update(model=model_used, ham_cikti=raw)
        review, problems, warnings = photo_review.validate_photo_output(llm_advisor.parse_output(raw))
        entry.update(sorunlar=problems, uyarilar=warnings)
    except llm_advisor.LlmError as error:
        review, problems, warnings = None, [str(error)], []
        entry["hata"] = str(error)

    entry["kullanilan"] = "yapay_zeka" if review else "kullanilmadi"
    _write_log(config, entry)
    if review is None:
        log.warning("Fotoğraf incelemesi kullanılamadı (ürün #%s): %s", product.id, "; ".join(problems))
        raise ServiceError("Fotoğraf incelemesi yapılamadı: " + "; ".join(problems))
    review.model = entry["model"] or ""
    return review, warnings
