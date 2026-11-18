"""Fiyat serisi hazırlama ve trend hesabı (Hafta 10) — YAPAY ZEKÂ KULLANMAZ.

Bu dosya iki iş yapar:
  1) analyze(): Fiyat serisinden sayısal göstergeler çıkarır (doğrusal regresyon eğimi,
     7 günlük değişim, oynaklık, 7 gün sonrası için tahmin).
  2) rule_based_advice(): Bu göstergelerden basit kurallarla satış zamanı önerisi üretir.

Neden yapay zekâdan ayrı?
  - Yapay zekâ çıktısını DOĞRULARKEN ölçü olarak kullanılır (llm_advisor.validate_output).
  - API anahtarı yoksa, API hata verirse ya da çıktı hatalıysa yedek (fallback) olarak kullanılır.
  - "Bu işi yapay zekâ olmadan yapabilir miydin?" sorusunun cevabıdır: evet, bu kadarını.

DOĞRUSAL REGRESYON (en küçük kareler):
  x = gün sırası (0, 1, 2, ...), y = fiyat. y = a + b·x doğrusunu bulur.
  b (eğim) = Σ(x - x̄)(y - ȳ) / Σ(x - x̄)²   -> günde kaç TL artıyor/azalıyor
  a        = ȳ - b·x̄
  R²       = 1 - Σ(y - ŷ)² / Σ(y - ȳ)²       -> doğru, veriyi ne kadar iyi açıklıyor (0-1)
"""
from dataclasses import dataclass, field
from statistics import mean, pstdev

from app.models import Trend

FORECAST_DAYS = 7
TREND_THRESHOLD_PCT = 3.0   # 7 günde %3'ten fazla değişim bekleniyorsa "yükseliyor/düşüyor"


@dataclass
class TrendStats:
    points: int
    first_date: object
    last_date: object
    last_price: float
    min_price: float
    max_price: float
    mean_last7: float
    mean_prev7: float
    change_7d_pct: float        # son 7 gün ortalaması, önceki 7 güne göre %
    slope_per_day: float        # TL/gün
    r2: float
    volatility_pct: float       # standart sapma / ortalama · 100 (son 14 gün)
    forecast_price: float       # 7 gün sonrası (regresyon doğrusu üzerinden)
    forecast_change_pct: float  # tahminin son fiyata göre farkı %
    trend: str                  # up / down / stable


@dataclass
class Advice:
    trend: str
    predicted_price: float
    confidence: float
    recommendation: str
    reasons: list = field(default_factory=list)
    source: str = "rule"        # "rule" (kural tabanlı) veya "llm" (yapay zekâ)


def linear_regression(ys):
    """ys: fiyat listesi (x = 0, 1, 2 ...). Dönüş: (eğim, kesişim, r2)."""
    n = len(ys)
    xs = range(n)
    x_bar, y_bar = (n - 1) / 2, mean(ys)
    sxx = sum((x - x_bar) ** 2 for x in xs)
    sxy = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = y_bar - slope * x_bar
    ss_tot = sum((y - y_bar) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, intercept, max(0.0, r2)


def classify(change_pct):
    if change_pct > TREND_THRESHOLD_PCT:
        return Trend.UP
    if change_pct < -TREND_THRESHOLD_PCT:
        return Trend.DOWN
    return Trend.STABLE


def analyze(series, window=21):
    """series: [(tarih, fiyat), ...] eskiden yeniye. En az 14 nokta olmalı (çağıran kontrol eder).

    Trend için SON `window` gün kullanılır: 60 günün tamamı mevsim dalgasını düzleştirir,
    satış kararı ise yakın geçmişe bağlıdır.
    """
    prices = [price for _, price in series]
    recent = prices[-window:]
    slope, intercept, r2 = linear_regression(recent)
    last = prices[-1]
    forecast = intercept + slope * (len(recent) - 1 + FORECAST_DAYS)
    forecast = max(forecast, 0.01)
    forecast_change = (forecast - last) / last * 100
    last14 = prices[-14:]
    return TrendStats(
        points=len(prices),
        first_date=series[0][0],
        last_date=series[-1][0],
        last_price=round(last, 2),
        min_price=round(min(prices), 2),
        max_price=round(max(prices), 2),
        mean_last7=round(mean(prices[-7:]), 2),
        mean_prev7=round(mean(prices[-14:-7]), 2),
        change_7d_pct=round((mean(prices[-7:]) - mean(prices[-14:-7])) / mean(prices[-14:-7]) * 100, 2),
        slope_per_day=round(slope, 3),
        r2=round(r2, 3),
        volatility_pct=round(pstdev(last14) / mean(last14) * 100, 2),
        forecast_price=round(forecast, 2),
        forecast_change_pct=round(forecast_change, 2),
        trend=classify(forecast_change),
    )


def rule_based_advice(stats, unit="kg"):
    """Göstergelerden kural tabanlı öneri (yapay zekâsız yedek)."""
    reasons = [
        f"Son 7 günün ortalaması önceki haftaya göre %{stats.change_7d_pct:+.1f} değişti.",
        f"Son {min(stats.points, 21)} günün eğilimi günde {stats.slope_per_day:+.2f} TL.",
    ]
    # Güven: doğru veriye ne kadar uyuyorsa (R²) ve fiyat ne kadar sakinse o kadar yüksek
    confidence = 0.35 + 0.4 * stats.r2 - min(stats.volatility_pct, 15) / 100
    confidence = round(min(0.8, max(0.2, confidence)), 2)

    if stats.trend == Trend.UP:
        text = (f"Hal fiyatı yükseliyor (7 gün sonra ≈ {stats.forecast_price:.2f} TL/{unit}). "
                "Stok durumunuz izin veriyorsa satışı birkaç gün erteleyebilir veya ilan fiyatını "
                "kademeli artırabilirsiniz.")
    elif stats.trend == Trend.DOWN:
        text = (f"Hal fiyatı düşüyor (7 gün sonra ≈ {stats.forecast_price:.2f} TL/{unit}). "
                "Elinizdeki ürünü bekletmeden şimdi satmanız daha avantajlı olabilir.")
    else:
        text = (f"Hal fiyatı yatay seyrediyor (≈ {stats.forecast_price:.2f} TL/{unit}). "
                "Satış zamanını fiyat değil, ürünün tazeliği ve stok durumu belirlemeli.")
    if stats.volatility_pct > 8:
        reasons.append(f"Fiyat oynak (%{stats.volatility_pct:.1f}); tahminin güveni düşük.")
    return Advice(stats.trend, stats.forecast_price, confidence, text, reasons, source="rule")
