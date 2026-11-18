"""Ödeme API istemcisi (Hafta 9).

İki istemci aynı arayüze sahiptir:
    charge(amount, card, idempotency_key, description) -> ChargeResult
    refund(transaction_ref, amount, idempotency_key)    -> ChargeResult

  - HttpPaymentGateway: gerçek ödeme sağlayıcısının REST API'si (PAYMENT_API_URL).
  - MockPaymentGateway: TEST MODU. Gerçek para çekilmez; sonucu kart numarası belirler
    (ödeme sağlayıcılarının "sandbox" ortamlarındaki test kartları gibi).

GÜVENLİK
  - Kart numarası ve CVC veri tabanına YAZILMAZ, günlüğe (log) YAZILMAZ. Sadece bu
    istekte sağlayıcıya iletilir. Biz yalnızca sağlayıcının verdiği işlem numarasını saklarız.
  - API anahtarı "Authorization" başlığında gider. Gizli anahtar (secret) HİÇ gönderilmez;
    istek gövdesinin HMAC-SHA256 imzasını üretmekte kullanılır. Sağlayıcı aynı imzayı
    hesaplayıp isteğin bizden geldiğini ve yolda değişmediğini anlar.
  - "Idempotency-Key": Ödeme isteği zaman aşımına uğrarsa yeniden denenir. Aynı anahtarla
    gelen ikinci isteği sağlayıcı YENİ ödeme saymaz, ilk sonucu döndürür. Böylece
    müşteriden iki kez para çekilmez.
"""
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.integrations.http import ApiResponseError, ApiServerError, ApiTimeoutError, request_json


@dataclass(frozen=True)
class CardInfo:
    holder: str
    number: str        # yalnızca rakamlar
    exp_month: int
    exp_year: int      # 4 haneli
    cvc: str

    @property
    def last4(self):
        return self.number[-4:]


@dataclass(frozen=True)
class ChargeResult:
    success: bool
    transaction_ref: str | None = None
    error_code: str | None = None
    message: str | None = None


# --- TEST MODU ------------------------------------------------------------------------

# Test kartları (ödeme formunda da gösterilir). Her biri farklı bir durumu dener.
TEST_CARDS = {
    "4111111111111111": ("success", "Başarılı ödeme"),
    "4000000000000002": ("declined", "Banka reddeder (yetersiz bakiye)"),
    "4000000000000119": ("timeout", "Banka yanıt vermez (zaman aşımı)"),
    "4000000000000259": ("server_error", "Ödeme servisi hata verir (500)"),
}


class MockPaymentGateway:
    name = "test"

    def __init__(self):
        self._processed = {}  # idempotency_key -> sonuç (gerçek sağlayıcının yaptığı gibi)

    def charge(self, amount, card, idempotency_key, description=""):
        if idempotency_key in self._processed:
            return self._processed[idempotency_key]

        behaviour = TEST_CARDS.get(card.number, ("success", ""))[0]
        if behaviour == "timeout":
            raise ApiTimeoutError("Test kartı: zaman aşımı benzetimi")
        if behaviour == "server_error":
            raise ApiServerError("Test kartı: sunucu hatası benzetimi", 500)
        if behaviour == "declined":
            result = ChargeResult(False, error_code="insufficient_funds",
                                  message="Kartın bakiyesi yetersiz.")
        else:
            result = ChargeResult(True, transaction_ref=f"TEST-{uuid.uuid4().hex[:12].upper()}")
        self._processed[idempotency_key] = result
        return result

    def refund(self, transaction_ref, amount, idempotency_key):
        return ChargeResult(True, transaction_ref=transaction_ref)


# --- Gerçek sağlayıcı -----------------------------------------------------------------

class HttpPaymentGateway:
    """Genel bir REST ödeme API'si.

    POST {PAYMENT_API_URL}/payments
        gövde : {"amount": "123.45", "currency": "TRY", "description": "...", "card": {...}}
        yanıt : {"id": "pay_...", "status": "succeeded" | "declined",
                 "error": {"code": "...", "message": "..."}}
    POST {PAYMENT_API_URL}/payments/{id}/refunds
        gövde : {"amount": "123.45"}
        yanıt : {"id": "...", "status": "succeeded" | "failed"}
    """

    name = "api"

    def __init__(self, base_url, api_key, secret_key, timeout=10, max_retries=2, session=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session

    def _post(self, path, body, idempotency_key):
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(self.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "X-Signature": signature,
        }
        # data=raw: imzalanan metin ile gönderilen metin BİREBİR aynı olmalı
        return request_json("POST", f"{self.base_url}{path}", data=raw, headers=headers,
                            timeout=self.timeout, max_retries=self.max_retries, session=self.session)

    def charge(self, amount, card, idempotency_key, description=""):
        body = {
            "amount": str(Decimal(amount).quantize(Decimal("0.01"))),
            "currency": "TRY",
            "description": description[:100],
            "card": {"holder": card.holder, "number": card.number,
                     "exp_month": card.exp_month, "exp_year": card.exp_year, "cvc": card.cvc},
        }
        return _parse_result(self._post("/payments", body, idempotency_key))

    def refund(self, transaction_ref, amount, idempotency_key):
        body = {"amount": str(Decimal(amount).quantize(Decimal("0.01")))}
        return _parse_result(self._post(f"/payments/{transaction_ref}/refunds", body, idempotency_key),
                             default_ref=transaction_ref)


def _parse_result(payload, default_ref=None):
    """Sağlayıcı yanıtını doğrular. Beklenmeyen biçim -> ApiResponseError."""
    if not isinstance(payload, dict) or payload.get("status") not in ("succeeded", "declined", "failed"):
        raise ApiResponseError("Ödeme yanıtında geçerli 'status' alanı yok")
    if payload["status"] == "succeeded":
        ref = payload.get("id") or default_ref
        if not isinstance(ref, str) or not ref:
            raise ApiResponseError("Başarılı ödeme yanıtında işlem numarası (id) yok")
        return ChargeResult(True, transaction_ref=ref[:100])
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    return ChargeResult(False, error_code=str(error.get("code") or "declined")[:50],
                        message=str(error.get("message") or "Ödeme banka tarafından reddedildi.")[:200])


_mock_gateway = MockPaymentGateway()  # süreç boyunca tek örnek (idempotency kaydı korunsun)


def get_payment_gateway(config):
    if config.get("USE_MOCK_APIS", True) or not config.get("PAYMENT_API_URL"):
        return _mock_gateway
    return HttpPaymentGateway(config["PAYMENT_API_URL"], config.get("PAYMENT_API_KEY", ""),
                              config.get("PAYMENT_SECRET_KEY", ""),
                              timeout=config.get("PAYMENT_API_TIMEOUT", 10),
                              max_retries=config.get("API_MAX_RETRIES", 2))
