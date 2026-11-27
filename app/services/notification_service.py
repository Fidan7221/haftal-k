"""Bildirimler (Hafta 12).

TETİKLEYİCİLER (bildirim neye göre, kime gider?):
  Olay                                   Kime              Nereden çağrılır
  ------------------------------------   ---------------   --------------------------------------
  Sipariş ödendi                          Üretici           payment_service.pay_order
  Sipariş kargoya verildi                 Müşteri           order_service.change_status
  Sipariş teslim edildi                   Müşteri + üretici order_service.change_status
  Sipariş iptal edildi (iade)             Karşı taraf       order_service.change_status
  İlan stoğu eşiğin altına İNDİ / bitti   Üretici           order_service.checkout
  Yeni değerlendirme                      Üretici           review_service.create_review

KURALLAR:
  - Bildirimi işlemi yapan kişinin kendisine göndermeyiz (müşteri iptal ettiyse üreticiye gider).
  - Bekleyen (ödenmemiş) sipariş için bildirim yok: ödeme hiç gelmeyebilir, üretici boşuna hazırlanmasın.
  - Stok uyarısı yalnızca eşik İLK KEZ aşıldığında gider (önce > eşik, şimdi ≤ eşik); her satışta tekrarlanmaz.
  - notify() COMMIT ETMEZ: bildirim olayla aynı işlemde kaydedilir. Olay geri alınırsa bildirim de oluşmaz.
"""
from decimal import Decimal

from flask import url_for

from app.extensions import db
from app.models import Notification, NotificationKind as Kind

LOW_STOCK_THRESHOLD = Decimal("5")  # producer_service.LOW_STOCK_THRESHOLD ile aynı (panel uyarısı)


def _url(endpoint, **values):
    """Bildirimden tıklanınca gidilecek site içi adres. İstek dışında (CLI) adres üretilemezse None."""
    try:
        return url_for(endpoint, **values)
    except RuntimeError:
        return None


def notify(user, kind, message, link=None):
    if user is None:
        return None
    notification = Notification(user=user, kind=kind, message=message[:255], link=link)
    db.session.add(notification)
    return notification


# --- Olaylar ------------------------------------------------------------------------------------

def order_paid(order):
    producer = order.producer
    if producer:
        notify(producer.user, Kind.ORDER_PAID,
               f"Sipariş #{order.id} ödendi ({order.total_amount:.2f} TL). Kargoya hazırlayabilirsiniz.",
               _url("order.producer_detail", order_id=order.id))


def order_shipped(order):
    notify(order.customer, Kind.ORDER_SHIPPED,
           f"Siparişiniz #{order.id} kargoya verildi.", _url("order.customer_detail", order_id=order.id))


def order_delivered(order):
    notify(order.customer, Kind.ORDER_DELIVERED,
           f"Siparişiniz #{order.id} teslim edildi. Ürünleri değerlendirebilirsiniz.",
           _url("order.customer_detail", order_id=order.id))
    if order.producer:
        notify(order.producer.user, Kind.ORDER_DELIVERED, f"Sipariş #{order.id} müşteriye teslim edildi.",
               _url("order.producer_detail", order_id=order.id))


def order_cancelled(order, by_role, refunded=False):
    """by_role: "customer" / "producer" / "admin". İşlemi yapana değil, karşı tarafa gider."""
    refund_note = " Ödeme iade edildi." if refunded else ""
    if by_role != "customer":
        notify(order.customer, Kind.ORDER_CANCELLED, f"Siparişiniz #{order.id} iptal edildi.{refund_note}",
               _url("order.customer_detail", order_id=order.id))
    if by_role != "producer" and order.producer:
        who = "Müşteri" if by_role == "customer" else "Yönetici"
        notify(order.producer.user, Kind.ORDER_CANCELLED,
               f"{who} sipariş #{order.id}'i iptal etti; stok ilana geri eklendi.",
               _url("order.producer_detail", order_id=order.id))


def stock_changed(listing, before, after):
    """Yalnızca eşik ilk kez aşıldığında bildirir."""
    owner = listing.product.producer.user
    link = _url("listing.my_listings")
    if after <= 0 < before:
        notify(owner, Kind.STOCK_OUT, f"'{listing.title}' ilanının stoğu bitti; ilan satıştan kalktı.", link)
    elif after <= LOW_STOCK_THRESHOLD < before:
        notify(owner, Kind.STOCK_LOW,
               f"'{listing.title}' ilanında {after.normalize():f} {listing.product.unit} kaldı.", link)


def review_received(review):
    # review.producer commit'ten önce yüklenmemiş olabilir; üretici sipariş kaleminden alınır
    notify(review.order_item.producer.user, Kind.REVIEW,
           f"'{review.order_item.listing.title}' için {review.rating} yıldızlı yeni bir değerlendirme aldınız.",
           _url("producer.reviews"))


# --- Okuma ----------------------------------------------------------------------------------------

def unread_count(user):
    return db.session.execute(
        db.select(db.func.count(Notification.id)).filter_by(user_id=user.id, is_read=False)
    ).scalar()


def list_for(user, limit=50):
    return db.session.execute(
        db.select(Notification).filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ).scalars().all()


def get_own(user, notification_id):
    """Başkasının bildirimi -> None (rota 404 verir)."""
    return db.session.execute(
        db.select(Notification).filter_by(id=notification_id, user_id=user.id)
    ).scalar_one_or_none()


def mark_read(notification):
    notification.is_read = True
    db.session.commit()


def mark_all_read(user):
    db.session.execute(
        db.update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.session.commit()
