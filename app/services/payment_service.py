"""Ödeme akışı (Hafta 9).

AKIŞ (müşteri "Öde" der):
  1) Kontroller: sipariş bu müşterinin mi, durumu "ödeme bekleniyor" mu?
  2) Ödeme kaydı INITIATED olarak YAZILIR (commit). Neden harici çağrıdan ÖNCE?
     Sunucu tam ödeme sırasında çökerse bile "bir ödeme denemesi başladı" izi kalır.
  3) Ödeme API'si çağrılır (zaman aşımı + yeniden deneme + idempotency anahtarı).
  4a) Başarılı  -> ödeme SUCCESS, sipariş PAID (ödendi).
  4b) Reddedildi / zaman aşımı / servis hatası -> ödeme FAILED + hata mesajı.
      Sipariş "ödeme bekleniyor" durumunda KALIR, stok ayrılmış kalır;
      müşteri başka kartla tekrar deneyebilir ya da siparişi iptal edebilir (stok geri döner).

İADE: Ödenmiş sipariş iptal edilirse önce sağlayıcıdan iade istenir. İade başarısızsa
sipariş İPTAL EDİLMEZ (para müşteride değilken sipariş "iptal" görünmesin).
"""
import logging
import uuid
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.integrations.http import IntegrationError
from app.integrations.payment_api import get_payment_gateway
from app.models import OrderStatus, Payment, PaymentStatus
from app.services import notification_service
from app.services.errors import ServiceError

log = logging.getLogger(__name__)


def _gateway():
    return get_payment_gateway(current_app.config)


def is_test_mode():
    return getattr(_gateway(), "name", "") == "test"


def pay_order(user, order, card):
    if order.customer_id != user.id:
        raise ServiceError("Bu siparişi yalnızca sipariş sahibi ödeyebilir.")
    if order.status != OrderStatus.PENDING:
        raise ServiceError(f"'{order.status_label}' durumundaki sipariş için ödeme alınamaz.")

    gateway = _gateway()
    payment = order.payment
    if payment is None:
        payment = Payment(order=order)  # sipariş başına tek ödeme kaydı (order_id unique)
    # Önceki başarısız denemenin üzerine yazılır; son denemenin sonucu görünür
    payment.provider = gateway.name
    payment.amount = order.total_amount
    payment.status = PaymentStatus.INITIATED
    payment.error_message = None
    payment.transaction_ref = None
    db.session.add(payment)
    db.session.commit()  # 2) iz bırak

    # Bu denemeye özel anahtar: yeniden denemelerde AYNI kalır -> çift çekim olmaz
    idempotency_key = f"order-{order.id}-{uuid.uuid4().hex}"
    try:
        result = gateway.charge(order.total_amount, card, idempotency_key,
                                description=f"Tarladan Sofraya sipariş #{order.id}")
    except IntegrationError as error:
        # Kart bilgisi günlüğe yazılmaz; yalnızca sipariş no ve teknik ayrıntı
        log.warning("Ödeme hatası, sipariş #%s: %s", order.id, error.detail)
        _mark_failed(payment, error.user_message)
        raise ServiceError(f"Ödeme tamamlanamadı: {error.user_message} "
                           "Siparişiniz 'ödeme bekleniyor' durumunda; tekrar deneyebilirsiniz.") from None

    if not result.success:
        _mark_failed(payment, result.message or "Ödeme reddedildi.")
        raise ServiceError(f"Ödeme reddedildi: {result.message} Başka bir kartla tekrar deneyebilirsiniz.")

    payment.status = PaymentStatus.SUCCESS
    payment.transaction_ref = result.transaction_ref
    payment.paid_at = datetime.now(timezone.utc)
    order.status = OrderStatus.PAID
    notification_service.order_paid(order)  # Hafta 12: ödemeyle aynı işlemde kaydedilir
    db.session.commit()
    return payment


def _mark_failed(payment, message):
    payment.status = PaymentStatus.FAILED
    payment.error_message = (message or "")[:255]
    db.session.commit()


def refund_payment(payment):
    """Ödenmiş siparişin iadesi. Commit ETMEZ: çağıran (iptal işlemi) tek seferde kaydeder."""
    if payment is None or payment.status != PaymentStatus.SUCCESS:
        return
    try:
        result = _gateway().refund(payment.transaction_ref, payment.amount,
                                   idempotency_key=f"refund-{payment.transaction_ref}")
    except IntegrationError as error:
        log.warning("İade hatası, ödeme %s: %s", payment.transaction_ref, error.detail)
        raise ServiceError(f"İade yapılamadığı için sipariş iptal edilmedi: {error.user_message}") from None
    if not result.success:
        raise ServiceError(f"İade reddedildi, sipariş iptal edilmedi: {result.message}")
    payment.status = PaymentStatus.REFUNDED
