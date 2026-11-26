"""Hafta 10 testleri: yapay zekâ bileşeni (fiyat trendi ve satış zamanı önerisi).

Gerçek yapay zekâ API'si ÇAĞRILMAZ (para harcamaz, internete çıkmaz). Bunun yerine
llm_advisor.create_client sahte bir istemciyle değiştirilir; sahte istemci istediğimiz
yanıtı (doğru JSON, bozuk JSON, saçma fiyat, reddetme...) döndürür. Böylece
"AI çıktısı hatalıysa ne yapıyorsun?" sorusunun cevabı test edilmiş olur.

Çalıştırma: python -m pytest -v tests/test_ai.py
"""
import base64
import io
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.ai import llm_advisor, photo_review
from app.ai.trend import analyze, linear_regression, rule_based_advice
from app.extensions import db
from app.models import Category, MarketPrice, PricePrediction, Trend
from app.services import ai_service, price_service
from app.services.ai_service import MAX_DAILY_REFRESH, RULE_MODEL
from tests.conftest import register_and_login
from tests.test_shop import make_product

TODAY = date(2026, 11, 18)


def series(prices):
    start = TODAY - timedelta(days=len(prices) - 1)
    return [(start + timedelta(days=i), float(p)) for i, p in enumerate(prices)]


RISING = series([20 + i * 0.5 for i in range(30)])     # günde +0,5 TL
FALLING = series([40 - i * 0.5 for i in range(30)])
FLAT = series([25 + (0.2 if i % 2 else -0.2) for i in range(30)])


# --- 1) Sayısal analiz (yapay zekâsız) ---------------------------------------------------

def test_linear_regression_exact_line():
    slope, intercept, r2 = linear_regression([3, 5, 7, 9])  # y = 3 + 2x
    assert slope == pytest.approx(2) and intercept == pytest.approx(3) and r2 == pytest.approx(1)


@pytest.mark.parametrize("data, trend", [(RISING, Trend.UP), (FALLING, Trend.DOWN), (FLAT, Trend.STABLE)])
def test_analyze_detects_trend(data, trend):
    stats = analyze(data)
    assert stats.trend == trend
    assert stats.points == 30 and stats.last_date == TODAY


def test_analyze_forecast_follows_line():
    stats = analyze(RISING)
    assert stats.forecast_price == pytest.approx(34.5 + 7 * 0.5)
    assert stats.slope_per_day == pytest.approx(0.5)


@pytest.mark.parametrize("data, word", [(RISING, "yükseliyor"), (FALLING, "düşüyor"), (FLAT, "yatay")])
def test_rule_based_advice(data, word):
    advice = rule_based_advice(analyze(data))
    assert word in advice.recommendation and advice.source == "rule"
    assert 0.2 <= advice.confidence <= 0.8 and advice.reasons


# --- 2) Yapay zekâ çıktısını doğrulama ----------------------------------------------------

def good_output(**overrides):
    data = {"trend": "up", "predicted_price_7d": 37.5, "confidence": 0.7,
            "recommendation": "Fiyat yükseliyor, satışı birkaç gün erteleyebilirsiniz.",
            "reasons": ["Son 30 günde düzenli artış var."]}
    data.update(overrides)
    return data


def test_valid_output_accepted():
    advice, problems, warnings = llm_advisor.validate_output(good_output(), analyze(RISING))
    assert advice is not None and not problems and not warnings
    assert advice.source == "llm" and advice.predicted_price == 37.5


@pytest.mark.parametrize("overrides, problem", [
    ({"trend": "yukari"}, "Geçersiz trend"),
    ({"predicted_price_7d": 340.0}, "Gerçekçi değil"),          # 10 kat fiyat
    ({"predicted_price_7d": -1}, "pozitif"),
    ({"predicted_price_7d": "37"}, "pozitif"),                  # metin, sayı değil
    ({"confidence": 1.5}, "Güven"),
    ({"confidence": True}, "Güven"),                            # bool sayı sayılmaz
    ({"recommendation": ""}, "boş"),
    ({"recommendation": "Detaylar için https://ornek.com adresine gidin."}, "bağlantı"),
    ({"trend": "up", "predicted_price_7d": 30.0}, "çelişiyor"),  # yükseliyor deyip düşük fiyat
])
def test_invalid_output_rejected(overrides, problem):
    advice, problems, _ = llm_advisor.validate_output(good_output(**overrides), analyze(RISING))
    assert advice is None
    assert any(problem in p for p in problems)


def test_output_opposite_to_strong_data_rejected():
    # Veriler net düşüş gösteriyor; model "yükseliyor" diyor
    stats = analyze(FALLING)
    output = good_output(trend="up", predicted_price_7d=stats.last_price * 1.05)
    advice, problems, _ = llm_advisor.validate_output(output, stats)
    assert advice is None and any("veriler açıkça" in p for p in problems)


def test_mild_disagreement_lowers_confidence():
    stats = analyze(FLAT)
    output = good_output(trend="up", predicted_price_7d=stats.last_price * 1.04, confidence=0.9)
    advice, problems, warnings = llm_advisor.validate_output(output, stats)
    assert advice is not None and not problems
    assert advice.confidence == 0.5 and warnings


def test_prompt_contains_data_but_no_personal_info():
    stats = analyze(RISING)
    prompt = llm_advisor.build_prompt("Domates", "kg", RISING, stats)
    assert "Domates" in prompt and "TL/kg" in prompt
    assert RISING[0][0].isoformat() in prompt and "34.50" in prompt
    assert "@" not in prompt  # e-posta vb. yok


def test_parse_output_rejects_non_json():
    with pytest.raises(llm_advisor.LlmError):
        llm_advisor.parse_output("Tabii! İşte cevabım: yükseliyor")


# --- 3) Uçtan uca: servis + sahte yapay zekâ istemcisi ------------------------------------

class FakeClient:
    """anthropic.Anthropic yerine geçer. client.beta.messages.create(...) çağrısını kaydeder."""

    def __init__(self, text=None, stop_reason="end_turn", error=None):
        self.requests = []
        self.text, self.stop_reason, self.error = text, stop_reason, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        content = [SimpleNamespace(type="text", text=self.text)] if self.text is not None else []
        return SimpleNamespace(content=content, stop_reason=self.stop_reason, model=kwargs["model"])


@pytest.fixture
def producer_product(app, client, tmp_path):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", name="Salkım Domates")
    price_service.sync_prices(days=30)
    app.config["AI_LOG_PATH"] = str(tmp_path / "ai_gunlugu.jsonl")
    return product


@pytest.fixture
def fake_ai(app, monkeypatch):
    """Yapay zekâyı aç ve sahte istemciyi tak. fake_ai(text=..., ...) ile yanıt ayarlanır."""
    app.config["AI_ENABLED"] = True

    def install(**kwargs):
        client = FakeClient(**kwargs)
        monkeypatch.setattr(llm_advisor, "create_client", lambda config: client)
        return client
    return install


def _matching_output(product):
    stats = analyze(price_service.price_series("Domates"))
    return json.dumps({"trend": stats.trend, "predicted_price_7d": stats.forecast_price,
                       "confidence": 0.66, "recommendation": "Sahte model önerisi: ürününüzü planlı satın.",
                       "reasons": ["Test gerekçesi"]})


def test_match_market_name(producer_product):
    assert price_service.match_market_name(producer_product) == "Domates"


@pytest.mark.parametrize("name, category, expected", [
    ("Kapya Biber", "Biber", "Biber"), ("Çiçek Balı", "Çiçek Balı", "Bal"),
    ("Köy Tereyağı", "Tereyağı", "Tereyağı"), ("Gün Kurusu Kayısı", "Kayısı", "Kayısı"),
    ("ELMA", "Meyve", "Elma"), ("Balkabağı", "Sebze", None),  # "bal" ile eşleşmemeli
])
def test_match_market_name_cases(app, monkeypatch, name, category, expected):
    monkeypatch.setattr(price_service, "market_names", lambda: ["Domates", "Biber", "Bal", "Tereyağı",
                                                                "Kayısı", "Elma"])
    product = SimpleNamespace(name=name, category=SimpleNamespace(name=category))
    assert price_service.match_market_name(product) == expected


def test_ai_disabled_uses_rule_based(producer_product):
    result = ai_service.suggest_for_product(producer_product)
    assert not result.used_ai and result.prediction.model_name == RULE_MODEL
    assert any("ANTHROPIC_API_KEY" in note for note in result.notes)
    assert PricePrediction.query.count() == 1


def test_same_day_uses_saved_prediction(producer_product, fake_ai):
    fake = fake_ai(text=_matching_output(producer_product))
    ai_service.suggest_for_product(producer_product)
    second = ai_service.suggest_for_product(producer_product)
    assert second.from_cache and len(fake.requests) == 1  # API ikinci kez çağrılmadı
    assert PricePrediction.query.count() == 1


def test_refresh_limit(producer_product):
    for _ in range(MAX_DAILY_REFRESH):
        ai_service.suggest_for_product(producer_product, refresh=True)
    with pytest.raises(Exception, match="en fazla"):
        ai_service.suggest_for_product(producer_product, refresh=True)


def test_valid_ai_output_is_used_and_logged(app, producer_product, fake_ai):
    fake = fake_ai(text=_matching_output(producer_product))
    result = ai_service.suggest_for_product(producer_product)
    assert result.used_ai and result.prediction.model_name == "claude-opus-5-5"
    assert result.advice.recommendation.startswith("Sahte model önerisi")

    request = fake.requests[0]
    assert request["output_config"]["format"]["type"] == "json_schema"  # yapılandırılmış çıktı
    assert request["system"] == llm_advisor.SYSTEM_PROMPT

    with open(app.config["AI_LOG_PATH"], encoding="utf-8") as file:
        entry = json.loads(file.readline())
    assert entry["kullanilan"] == "yapay_zeka" and entry["istem"] and entry["ham_cikti"]


@pytest.mark.parametrize("kwargs, reason", [
    ({"text": "bu json değil"}, "geçerli JSON değil"),
    ({"text": json.dumps({"trend": "up", "predicted_price_7d": 9999, "confidence": 0.9,
                          "recommendation": "Çok yükselecek, bekleyin!", "reasons": []})}, "Gerçekçi değil"),
    ({"text": "", "stop_reason": "refusal"}, "refusal"),
    ({"text": "{\"trend\": \"up\"", "stop_reason": "max_tokens"}, "yarıda kesildi"),
    ({"text": ""}, "boş yanıt"),
])
def test_bad_ai_output_falls_back_to_rules(app, producer_product, fake_ai, kwargs, reason):
    fake_ai(**kwargs)
    result = ai_service.suggest_for_product(producer_product)
    assert not result.used_ai and result.prediction.model_name == RULE_MODEL
    assert any(reason in note for note in result.notes)
    entries = ai_service.read_log()
    assert entries[0]["kullanilan"] == "kural_tabanli"


def test_api_errors_fall_back_to_rules(producer_product, fake_ai):
    import anthropic
    import httpx2 as httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_ai(error=anthropic.APITimeoutError(request=request))
    result = ai_service.suggest_for_product(producer_product)
    assert not result.used_ai and any("zaman aşımı" in n for n in result.notes)


def test_product_without_market_price(app, client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", name="Kivi")
    product.category = Category.query.filter_by(slug="meyve").one()  # ne adı ne kategorisi eşleşir
    db.session.commit()
    price_service.sync_prices(days=20)
    assert MarketPrice.query.count() > 0  # fiyat VAR ama bu ürüne ait değil
    page = client.get(f"/uretici/urunler/{product.id}/fiyat-onerisi").get_data(as_text=True)
    assert "eşleşen ürün bulunamadı" in page


def test_not_enough_data(app, client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", name="Domates")
    price_service.sync_prices(days=5)
    page = client.get(f"/uretici/urunler/{product.id}/fiyat-onerisi").get_data(as_text=True)
    assert "en az 14 günlük fiyat" in page


# --- 4) Sayfa ve yetki --------------------------------------------------------------------

def test_suggestion_page_and_refresh(client, producer_product):
    page = client.get(f"/uretici/urunler/{producer_product.id}/fiyat-onerisi").get_data(as_text=True)
    assert "Fiyat Trendi ve Satış Zamanı" in page and "<polyline" in page
    assert "Kural tabanlı öneri" in page and "Bu bir <strong>öneridir</strong>" in page
    refreshed = client.post(f"/uretici/urunler/{producer_product.id}/fiyat-onerisi", follow_redirects=True)
    assert "Öneri yeniden hesaplandı" in refreshed.get_data(as_text=True)
    assert PricePrediction.query.count() == 2


def test_other_producer_gets_404(client, producer_product):
    client.post("/auth/logout")
    register_and_login(client, "baska@test.com", farm_name="Başka Çiftlik")
    assert client.get(f"/uretici/urunler/{producer_product.id}/fiyat-onerisi").status_code == 404


def test_customer_gets_403(client, producer_product):
    client.post("/auth/logout")
    register_and_login(client, "musteri@test.com", role="customer")
    assert client.get(f"/uretici/urunler/{producer_product.id}/fiyat-onerisi").status_code == 403


def test_admin_ai_log_page(app, client, producer_product, fake_ai):
    from app.services.auth_service import create_admin_user
    fake_ai(text="bozuk")
    ai_service.suggest_for_product(producer_product)
    client.post("/auth/logout")
    create_admin_user("Yönetici", "yonetici@test.com", "Parola123")
    client.post("/auth/login", data={"email": "yonetici@test.com", "password": "Parola123"})
    page = client.get("/yonetici/ai-gunlugu").get_data(as_text=True)
    assert "Domates" in page and "Reddedildi" in page and "geçerli JSON değil" in page


# --- Ücretsiz sağlayıcı: Google Gemini ----------------------------------------------------
# Gerçek Gemini çağrılmaz: llm_advisor.gemini_request sahte fonksiyonla değiştirilir.

def _gemini_response(text, finish="STOP"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
            "modelVersion": "gemini-test"}


@pytest.fixture
def fake_gemini(app, monkeypatch):
    app.config.update(AI_ENABLED=True, AI_PROVIDER="gemini", AI_MODEL="gemini-test")
    monkeypatch.setenv("GEMINI_API_KEY", "test-anahtari")
    calls = []

    def install(*responses):
        queue = list(responses)

        def fake_request(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": body})
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        monkeypatch.setattr(llm_advisor, "gemini_request", fake_request)
        return calls
    return install


def test_gemini_output_is_used(producer_product, fake_gemini):
    calls = fake_gemini(_gemini_response(_matching_output(producer_product)))
    result = ai_service.suggest_for_product(producer_product)
    assert result.used_ai and result.prediction.model_name == "gemini-test"
    call = calls[0]
    assert call["headers"]["x-goog-api-key"] == "test-anahtari"    # anahtar başlıkta
    assert "test-anahtari" not in call["url"]                       # adreste değil
    assert call["body"]["generationConfig"]["responseMimeType"] == "application/json"
    # Düşünme "low": düşünme token'ları cevabı yarıda kesmesin (MAX_TOKENS), yanıt hızlı gelsin
    assert call["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert call["body"]["systemInstruction"]["parts"][0]["text"] == llm_advisor.SYSTEM_PROMPT


def test_gemini_retries_without_schema_on_400(producer_product, fake_gemini):
    from app.integrations.http import ApiClientError

    calls = fake_gemini(ApiClientError("400", 400), _gemini_response(_matching_output(producer_product)))
    result = ai_service.suggest_for_product(producer_product)
    assert result.used_ai and len(calls) == 2
    assert "responseSchema" not in calls[1]["body"]["generationConfig"]
    assert "thinkingConfig" not in calls[1]["body"]["generationConfig"]


@pytest.mark.parametrize("response, reason", [
    (_gemini_response("", "MAX_TOKENS"), "yarıda kesildi"),
    (_gemini_response("", "SAFETY"), "yanıtlamadı"),
    ({"candidates": []}, "boş yanıt"),
    (_gemini_response("json değil"), "geçerli JSON değil"),
])
def test_bad_gemini_output_falls_back(producer_product, fake_gemini, response, reason):
    fake_gemini(response)
    result = ai_service.suggest_for_product(producer_product)
    assert not result.used_ai and any(reason in note for note in result.notes)


def test_gemini_rate_limit_falls_back(producer_product, fake_gemini):
    from app.integrations.http import ApiRateLimitError

    fake_gemini(ApiRateLimitError("429", 429))
    result = ai_service.suggest_for_product(producer_product)
    assert not result.used_ai and any("hız sınırı" in note for note in result.notes)


# --- Fotoğraf incelemesi (v0.10.4): yapay zekâ ürün fotoğrafına bakar -----------------------
# Gerçek model çağrılmaz. Fotoğraf veri tabanına yüklenir, sahte Gemini/Claude cevap verir.

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _photo_output(**overrides):
    data = {"shows_product": True, "detected": "Kırmızı kapya biberler, ahşap kasada",
            "freshness": "taze", "photo_quality": 4,
            "strengths": ["Renkler canlı"], "issues": ["Arka plan dağınık"],
            "tips": ["Gün ışığında, sade bir arka planla çekin"],
            "summary": "Biberler taze görünüyor; sade bir arka plan fotoğrafı daha çekici yapar."}
    data.update(overrides)
    return data


@pytest.fixture
def photo_product(app, client):
    ai_service._photo_review_counts.clear()  # günlük sayaç bellekte; testler birbirini etkilemesin
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", name="Kapya Biber")
    client.post(f"/uretici/urunler/{product.id}/duzenle", content_type="multipart/form-data", data={
        "category_id": str(product.category_id), "name": "Kapya Biber", "unit": "kg",
        "stock_quantity": "100", "description": "", "is_active": "y", "image": (io.BytesIO(PNG), "biber.png")})
    db.session.refresh(product)
    assert product.image_path.startswith("db/")
    return product


def test_photo_review_sends_image_and_shows_result(client, photo_product, fake_gemini):
    calls = fake_gemini(_gemini_response(json.dumps(_photo_output())))
    page = client.post(f"/uretici/urunler/{photo_product.id}/fotograf-incelemesi").get_data(as_text=True)
    assert "Taze görünüyor" in page and "Fotoğraf kalitesi: 4/5" in page
    assert "sade bir arka planla" in page and "Model: gemini-test" in page

    body = calls[0]["body"]
    image_part = body["contents"][0]["parts"][0]["inlineData"]       # fotoğraf isteğin içinde
    assert image_part["mimeType"] == "image/png" and base64.b64decode(image_part["data"]) == PNG
    assert body["systemInstruction"]["parts"][0]["text"] == photo_review.PHOTO_SYSTEM_PROMPT
    assert body["generationConfig"]["responseSchema"] == photo_review.PHOTO_GEMINI_SCHEMA


def test_photo_review_with_claude_sends_image_block(photo_product, app, monkeypatch):
    app.config["AI_ENABLED"] = True
    fake = FakeClient(text=json.dumps(_photo_output()))
    monkeypatch.setattr(llm_advisor, "create_client", lambda config: fake)
    review, _ = ai_service.review_product_photo(photo_product)
    content = fake.requests[0]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert fake.requests[0]["output_config"]["format"]["schema"] == photo_review.PHOTO_SCHEMA
    assert review.freshness == "taze"


@pytest.mark.parametrize("overrides, problem", [
    ({"freshness": "harika"}, "tazelik"),
    ({"photo_quality": 9}, "1-5"),
    ({"photo_quality": True}, "1-5"),
    ({"shows_product": "evet"}, "true/false"),
    ({"tips": []}, "'tips' listesi boş"),
    ({"summary": "Bak: https://ornek.com"}, "bağlantı"),
    ({"strengths": "renkli"}, "metin listesi"),
])
def test_invalid_photo_output_rejected(overrides, problem):
    review, problems, _ = photo_review.validate_photo_output(_photo_output(**overrides))
    assert review is None and any(problem in p for p in problems)


def test_photo_not_showing_product_is_flagged():
    review, problems, warnings = photo_review.validate_photo_output(
        _photo_output(shows_product=False, freshness="taze", detected="Bir kedi"))
    assert review is not None and not problems
    assert review.freshness == "belirsiz"          # ürün yoksa tazelik yorumlanamaz
    assert any("göstermiyor" in w for w in warnings)


def test_photo_review_failure_shows_reason_and_logs(app, client, photo_product, fake_gemini, tmp_path):
    app.config["AI_LOG_PATH"] = str(tmp_path / "ai.jsonl")
    fake_gemini(_gemini_response("bozuk"))
    page = client.post(f"/uretici/urunler/{photo_product.id}/fotograf-incelemesi").get_data(as_text=True)
    assert "Fotoğraf incelemesi yapılamadı" in page and "geçerli JSON değil" in page
    entry = ai_service.read_log()[0]
    assert entry["tur"] == "fotograf" and entry["kullanilan"] == "kullanilmadi"
    assert "image/png" in entry["istem"] and "iVBOR" not in entry["istem"]  # fotoğrafın kendisi günlükte yok


def test_photo_review_needs_ai_and_photo(client, app, photo_product):
    page = client.post(f"/uretici/urunler/{photo_product.id}/fotograf-incelemesi").get_data(as_text=True)
    assert "yapay zekâ açık olmalı" in page            # AI kapalı (testlerde varsayılan)

    app.config["AI_ENABLED"] = True
    other = make_product("ciftci@test.com", name="Fotoğrafsız Domates")
    page = client.post(f"/uretici/urunler/{other.id}/fotograf-incelemesi").get_data(as_text=True)
    assert "fotoğrafı yok" in page


def test_photo_review_daily_limit(photo_product, fake_gemini):
    fake_gemini(*[_gemini_response(json.dumps(_photo_output()))] * ai_service.MAX_DAILY_PHOTO_REVIEWS)
    ai_service._photo_review_counts.clear()
    for _ in range(ai_service.MAX_DAILY_PHOTO_REVIEWS):
        ai_service.review_product_photo(photo_product)
    with pytest.raises(Exception, match="en fazla"):
        ai_service.review_product_photo(photo_product)
    ai_service._photo_review_counts.clear()


def test_photo_review_other_producer_404(client, photo_product):
    client.post("/auth/logout")
    register_and_login(client, "baska@test.com", farm_name="Başka Çiftlik")
    assert client.get(f"/uretici/urunler/{photo_product.id}/fotograf-incelemesi").status_code == 404
