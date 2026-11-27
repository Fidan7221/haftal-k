"""Bildirim modeli (notifications tablosu) — Hafta 12.

Bildirim, bir olay olduğunda (sipariş ödendi, kargoya verildi, stok azaldı, yeni değerlendirme...)
ilgili kullanıcı için oluşturulur ve olayla AYNI işlemde (transaction) kaydedilir: olay geri alınırsa
(rollback) bildirim de oluşmaz, "ödendi" bildirimi gelip ödemenin olmaması gibi bir tutarsızlık olmaz.
"""
from app.extensions import db
from app.models.base import BaseModel


class NotificationKind:
    ORDER_PAID = "order_paid"            # üreticiye
    ORDER_CANCELLED = "order_cancelled"  # karşı tarafa
    ORDER_SHIPPED = "order_shipped"      # müşteriye
    ORDER_DELIVERED = "order_delivered"  # müşteriye (değerlendirme daveti) ve üreticiye
    STOCK_LOW = "stock_low"              # üreticiye
    STOCK_OUT = "stock_out"              # üreticiye
    REVIEW = "review"                    # üreticiye

    ICONS = {
        ORDER_PAID: "bag-check", ORDER_CANCELLED: "x-circle", ORDER_SHIPPED: "truck",
        ORDER_DELIVERED: "box-seam", STOCK_LOW: "exclamation-triangle", STOCK_OUT: "slash-circle",
        REVIEW: "star",
    }


class Notification(BaseModel):
    __tablename__ = "notifications"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255))          # yalnızca site içi adres (url_for ile üretilir)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)

    user = db.relationship("User")

    @property
    def icon(self):
        return NotificationKind.ICONS.get(self.kind, "bell")
