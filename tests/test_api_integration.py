"""Hafta 9 testleri: harici API entegrasyonu (fiyat + ödeme) ve hata yönetimi.

Testler İNTERNETE ÇIKMAZ. Gerçek HTTP yerine sahte bir "oturum" (FakeSession) kullanılır;
böylece zaman aşımı, 429, 500 gibi durumlar istenildiği an üretilebilir.

Çalıştırma: python -m pytest -v tests/test_api_integration.py
"""
import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal

import pytest
import requests

from app.extensions import db
from app.integrations import http
from app.integrations.http import (
    ApiAuthError, ApiClientError, ApiRateLimitError, ApiResponseError, ApiServerError, ApiTimeoutError,
    request_json,
)
from app.integrations.payment_api import (
    CardInfo, HttpPaymentGateway, MockPaymentGateway, _mock_gateway,
)
from app.integrations.price_api import HalPriceClient, MockPriceClient, parse_items
from app.models import MarketPrice, Order, OrderStatus, Payment, PaymentStatus
from app.services import price_service
from app.services.auth_service import create_admin_user
from tests.test_shop import TEST_CARD, checkout, customer_with_cart, set_status, setup_listing


# --- Sahte HTTP oturumu ------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._body = body
        self._text = text
        self.headers = headers or {}

    def json(self):
        if self._text is not None:
            raise ValueError("JSON değil")
        return self._body


class FakeSession:
    """Sırayla verilen yanıtları döndürür; Exception ise fırlatır. Gelen istekleri kaydeder."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def waits(monkeypatch):
    """http.sleep gerçekten beklemesin; beklenen süreler listeye yazılsın."""
    recorded = []
    monkeypatch.setattr(http, "sleep", recorded.append)
    return recorded


# --- 1) Ortak HTTP katmanı: zaman aşımı, yeniden deneme, hız sınırı ------------------------

def test_timeout_is_retried_then_succeeds(waits):
    session = FakeSession(requests.Timeout(), FakeResponse(body={"ok": True}))
    assert request_json("GET", "https://api.test/x", timeout=1, session=session) == {"ok": True}
    assert len(session.calls) == 2
    assert all(call["timeout"] == 1 for call in session.calls)  # her istekte timeout var
    assert waits == [0.5]


def test_timeout_every_time_raises_after_max_retries(waits):
    session = FakeSession(*[requests.Timeout()] * 3)
    with pytest.raises(ApiTimeoutError):
        request_json("GET", "https://api.test/x", timeout=1, max_retries=2, session=session)
    assert len(session.calls) == 3  # 1 deneme + 2 tekrar
    assert waits == [0.5, 1.0]      # üstel bekleme


def test_rate_limit_respects_retry_after_header(waits):
    session = FakeSession(FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(body={"ok": 1}))
    request_json("GET", "https://api.test/x", timeout=1, session=session)
    assert waits == [2.0]


def test_rate_limit_wait_is_capped(waits):
    session = FakeSession(*[FakeResponse(429, headers={"Retry-After": "3600"})] * 2)
    with pytest.raises(ApiRateLimitError):
        request_json("GET", "https://api.test/x", timeout=1, max_retries=1, session=session)
    assert waits == [http.MAX_RETRY_AFTER]  # bir saat değil, en fazla 5 sn


def test_server_error_retried_then_fails(waits):
    session = FakeSession(*[FakeResponse(503)] * 3)
    with pytest.raises(ApiServerError):
        request_json("GET", "https://api.test/x", timeout=1, session=session)
    assert len(session.calls) == 3


@pytest.mark.parametrize("status, error", [(401, ApiAuthError), (403, ApiAuthError), (400, ApiClientError),
                                           (404, ApiClientError)])
def test_client_errors_are_not_retried(waits, status, error):
    session = FakeSession(FakeResponse(status, body={}))
    with pytest.raises(error):
        request_json("GET", "https://api.test/x", timeout=1, session=session)
    assert len(session.calls) == 1 and waits == []  # kalıcı hata: tekrar denemek boşuna


def test_non_json_response_raises(waits):
    with pytest.raises(ApiResponseError):
        request_json("GET", "https://api.test/x", timeout=1, session=FakeSession(FakeResponse(text="<html>")))


def test_user_message_hides_technical_details(waits):
    session = FakeSession(*[requests.Timeout()] * 3)
    with pytest.raises(ApiTimeoutError) as info:
        request_json("GET", "https://gizli.api.test/x?key=ABC", timeout=1, session=session)
    assert "gizli.api.test" in info.value.detail          # günlükte teknik ayrıntı var
    assert "gizli" not in info.value.user_message         # kullanıcı mesajında yok
    assert "ABC" not in info.value.user_message


# --- 2) Fiyat API'si: yanıt ayrıştırma ve anahtar kullanımı ------------------------------

def test_parse_items_skips_invalid_rows():
    payload = {"items": [
        {"product": "Domates", "unit": "kg", "min": 20, "max": 30, "avg": 25},
        {"product": "", "avg": 10},                                 # adı yok
        {"product": "Biber", "avg": -5},                            # negatif
        {"product": "Elma", "min": 40, "max": 30, "avg": 35},       # min > ort
        {"product": "Patates", "avg": "abc"},                       # sayı değil
        "bozuk satır",
        {"product": "Nohut", "avg": 70},                            # min/max yoksa ort kullanılır
    ]}
    quotes, skipped = parse_items(payload, date(2026, 11, 18))
    assert [q.product_name for q in quotes] == ["Domates", "Nohut"]
    assert skipped == 5
    assert quotes[1].min_price == quotes[1].max_price == Decimal("70.00")


def test_parse_items_rejects_wrong_shape():
    with pytest.raises(ApiResponseError):
        parse_items({"data": []}, date.today())


def test_price_client_sends_key_in_header_not_url(waits):
    session = FakeSession(FakeResponse(body={"items": [{"product": "Domates", "avg": 25}]}))
    client = HalPriceClient("https://hal.test/api/", "GIZLI-ANAHTAR", timeout=3, session=session)
    quotes, _ = client.fetch_day(date(2026, 11, 18))
    call = session.calls[0]
    assert call["url"] == "https://hal.test/api/prices"
    assert call["params"] == {"date": "2026-11-18"}
    assert call["headers"]["X-API-Key"] == "GIZLI-ANAHTAR"
    assert "GIZLI" not in call["url"] and quotes[0].avg_price == Decimal("25.00")


def test_mock_price_client_is_deterministic():
    day = date(2026, 11, 18)
    assert MockPriceClient().fetch_day(day) == MockPriceClient().fetch_day(day)


# --- 3) Fiyat senkronizasyonu --------------------------------------------------------------

def test_sync_prices_inserts_then_uses_cache(app):
    report = price_service.sync_prices(days=10, today=date(2026, 11, 18))
    assert report["days"] == 10 and report["inserted"] == 10 * 11 and not report["errors"]
    again = price_service.sync_prices(days=10, today=date(2026, 11, 18))
    assert again["days"] == 0 and again["cached_days"] == 10  # API tekrar çağrılmadı
    domates = MarketPrice.query.filter_by(product_name="Domates").first()
    assert domates.category is not None and domates.category.slug == "domates"


class BrokenClient:
    source = "hal_api"

    def __init__(self, error):
        self.error, self.calls = error, 0

    def fetch_day(self, day):
        self.calls += 1
        raise self.error


@pytest.mark.parametrize("error", [ApiAuthError("401"), ApiRateLimitError("429")])
def test_sync_stops_on_auth_or_rate_limit(app, monkeypatch, error):
    client = BrokenClient(error)
    monkeypatch.setattr(price_service, "get_price_client", lambda config: client)
    report = price_service.sync_prices(days=5)
    assert client.calls == 1 and len(report["errors"]) == 1  # zorlamaya devam etmedi


def test_sync_skips_failed_day_and_continues(app, monkeypatch):
    real = MockPriceClient()
    calls = []

    class Flaky:
        source = real.source

        def fetch_day(self, day):
            calls.append(day)
            if len(calls) == 2:
                raise ApiTimeoutError("zaman aşımı")
            return real.fetch_day(day)

    monkeypatch.setattr(price_service, "get_price_client", lambda config: Flaky())
    report = price_service.sync_prices(days=3)
    assert report["days"] == 2 and len(report["errors"]) == 1
    assert "zaman aşımı" in report["errors"][0]


def test_cli_fetch_prices(app):
    result = app.test_cli_runner().invoke(args=["fetch-prices", "--days", "3"])
    assert "yeni: 33" in result.output
    assert MarketPrice.query.count() == 33


def test_price_page(client):
    assert "Henüz fiyat verisi yok" in client.get("/hal-fiyatlari").get_data(as_text=True)
    price_service.sync_prices(days=8)
    page = client.get("/hal-fiyatlari").get_data(as_text=True)
    assert "Domates" in page and "örnek (test) verisidir" in page


def test_admin_sync_button_has_cooldown(app, client):
    create_admin_user("Yönetici", "yonetici@test.com", "Parola123")
    client.post("/auth/login", data={"email": "yonetici@test.com", "password": "Parola123"})
    app.config["PRICE_SYNC_COOLDOWN"] = 60
    first = client.post("/yonetici/fiyatlar/guncelle", follow_redirects=True).get_data(as_text=True)
    assert "Fiyat güncelleme: 30 gün çekildi" in first
    second = client.post("/yonetici/fiyatlar/guncelle", follow_redirects=True).get_data(as_text=True)
    assert "hız sınırı" in second


def test_customer_cannot_sync_prices(client):
    from tests.conftest import register_and_login
    register_and_login(client, "m@test.com", role="customer")
    assert client.post("/yonetici/fiyatlar/guncelle").status_code == 403


# --- 4) Ödeme API istemcisi ----------------------------------------------------------------

CARD = CardInfo("Deneme Kullanıcı", "4111111111111111", 12, 2039, "123")


def test_payment_request_is_signed_and_idempotent(waits):
    session = FakeSession(FakeResponse(body={"id": "pay_1", "status": "succeeded"}))
    gateway = HttpPaymentGateway("https://pay.test/v1", "PUB-KEY", "SECRET", session=session)
    result = gateway.charge(Decimal("150.5"), CARD, "order-7-abc")
    call = session.calls[0]
    assert result.success and result.transaction_ref == "pay_1"
    assert call["headers"]["Authorization"] == "Bearer PUB-KEY"
    assert call["headers"]["Idempotency-Key"] == "order-7-abc"
    expected = hmac.new(b"SECRET", call["data"].encode(), hashlib.sha256).hexdigest()
    assert call["headers"]["X-Signature"] == expected
    assert "SECRET" not in call["data"] and "SECRET" not in str(call["headers"])  # gizli anahtar gönderilmez
    assert json.loads(call["data"])["amount"] == "150.50"


def test_payment_declined_response(waits):
    session = FakeSession(FakeResponse(body={"status": "declined",
                                             "error": {"code": "card_declined", "message": "Kart reddedildi"}}))
    result = HttpPaymentGateway("https://pay.test", "k", "s", session=session).charge(1, CARD, "x")
    assert not result.success and result.error_code == "card_declined"


def test_payment_unexpected_response(waits):
    session = FakeSession(FakeResponse(body={"status": "succeeded"}))  # işlem numarası yok
    with pytest.raises(ApiResponseError):
        HttpPaymentGateway("https://pay.test", "k", "s", session=session).charge(1, CARD, "x")


def test_mock_gateway_idempotency():
    gateway = MockPaymentGateway()
    first = gateway.charge(10, CARD, "ayni-anahtar")
    assert gateway.charge(10, CARD, "ayni-anahtar") == first  # ikinci kez çekim yok


# --- 5) Ödeme akışı (uçtan uca) -------------------------------------------------------------

def _pending_order(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing)
    checkout(client)
    return Order.query.one()


def _pay(client, order, number):
    return client.post(f"/siparislerim/{order.id}/odeme",
                       data={**TEST_CARD, "card_number": number}, follow_redirects=True)


def test_successful_payment(client):
    order = _pending_order(client)
    page = _pay(client, order, "4111111111111111").get_data(as_text=True)
    assert "Ödeme alındı" in page
    assert order.status == OrderStatus.PAID
    assert order.payment.status == PaymentStatus.SUCCESS and order.payment.provider == "test"
    assert order.payment.transaction_ref.startswith("TEST-")


def test_declined_payment_keeps_order_pending_and_can_retry(client):
    order = _pending_order(client)
    page = _pay(client, order, "4000000000000002").get_data(as_text=True)
    assert "Ödeme reddedildi" in page
    assert order.status == OrderStatus.PENDING                 # sipariş bekliyor
    assert order.payment.status == PaymentStatus.FAILED
    assert "bakiyesi yetersiz" in order.payment.error_message
    _pay(client, order, "4111111111111111")                     # başka kartla tekrar
    assert order.status == OrderStatus.PAID
    assert Payment.query.count() == 1                           # aynı kayıt güncellendi


@pytest.mark.parametrize("number, text", [("4000000000000119", "zaman aşımı"),
                                          ("4000000000000259", "geçici bir sorun")])
def test_payment_api_failure_is_handled(client, number, text):
    order = _pending_order(client)
    page = _pay(client, order, number).get_data(as_text=True)
    assert text in page
    assert order.status == OrderStatus.PENDING and order.payment.status == PaymentStatus.FAILED


def test_invalid_card_never_reaches_api(client):
    order = _pending_order(client)
    page = _pay(client, order, "4111111111111112").get_data(as_text=True)  # Luhn hatalı
    assert "Kart numarası geçersiz" in page
    assert order.payment is None


def test_expired_card_rejected(client):
    order = _pending_order(client)
    page = client.post(f"/siparislerim/{order.id}/odeme", data={**TEST_CARD, "expiry": "01/20"},
                       follow_redirects=True).get_data(as_text=True)
    assert "süresi dolmuş" in page and order.payment is None


def test_card_number_is_not_stored(client):
    order = _pending_order(client)
    _pay(client, order, "4111111111111111")
    row = db.session.execute(db.select(Payment.__table__)).mappings().one()
    assert "4111" not in json.dumps({k: str(v) for k, v in row.items()})


def test_paid_status_cannot_be_set_without_payment(client):
    order = _pending_order(client)
    page = client.post(f"/siparis/{order.id}/durum", data={"new_status": OrderStatus.PAID},
                       follow_redirects=True).get_data(as_text=True)
    assert "ödeme formundan" in page
    assert order.status == OrderStatus.PENDING and order.payment is None


def test_cancel_paid_order_refunds(client):
    order = _pending_order(client)
    set_status(client, order, OrderStatus.PAID)
    set_status(client, order, OrderStatus.CANCELLED)
    assert order.status == OrderStatus.CANCELLED and order.payment.status == PaymentStatus.REFUNDED


def test_failed_refund_keeps_order(client, monkeypatch):
    order = _pending_order(client)
    set_status(client, order, OrderStatus.PAID)
    listing_stock = order.items[0].listing.stock_quantity

    def broken_refund(*args, **kwargs):
        raise ApiTimeoutError("iade zaman aşımı")

    monkeypatch.setattr(_mock_gateway, "refund", broken_refund)
    page = set_status(client, order, OrderStatus.CANCELLED).get_data(as_text=True)
    assert "İade yapılamadığı için sipariş iptal edilmedi" in page
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID and order.payment.status == PaymentStatus.SUCCESS
    assert order.items[0].listing.stock_quantity == listing_stock  # stok da geri eklenmedi


def test_other_customer_cannot_pay(client):
    order = _pending_order(client)
    client.post("/auth/logout")
    customer_with_cart(client, order.items[0].listing, email="baska@test.com")
    assert client.get(f"/siparislerim/{order.id}/odeme").status_code == 404
