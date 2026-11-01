"""Satış ilanı modeli (listings tablosu).

Bir ürün farklı dönemlerde farklı fiyat ve stokla ilana çıkabilir.
Sepet ve sipariş kalemleri ürüne değil, ilana bağlanır.
"""
from datetime import date

from app.extensions import db
from app.models.base import BaseModel


class ListingStatus:
    ACTIVE = "active"        # Satışta
    SOLD_OUT = "sold_out"    # Stok bitti
    CLOSED = "closed"        # Üretici kapattı veya süresi doldu

    ALL = (ACTIVE, SOLD_OUT, CLOSED)

    # Ekranda gösterilecek Türkçe adlar (Hafta 7)
    LABELS = {ACTIVE: "Satışta", SOLD_OUT: "Tükendi", CLOSED: "Kapalı"}


class Listing(BaseModel):
    __tablename__ = "listings"
    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_listing_price_positive"),
        db.CheckConstraint("stock_quantity >= 0", name="ck_listing_stock_positive"),
    )

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)          # birim fiyatı (TL)
    stock_quantity = db.Column(db.Numeric(10, 2), nullable=False)  # satılabilir miktar
    min_order_quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)
    start_date = db.Column(db.Date, default=date.today, nullable=False)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default=ListingStatus.ACTIVE, nullable=False, index=True)

    # --- İlişkiler ---
    product = db.relationship("Product", back_populates="listings")
    cart_items = db.relationship("CartItem", back_populates="listing")
    order_items = db.relationship("OrderItem", back_populates="listing")

    # --- Hafta 7: iş kuralı yardımcıları ---
    @property
    def is_expired(self):
        """Bitiş tarihi geçmiş mi? (bitiş tarihi boşsa ilan süresizdir)"""
        return self.end_date is not None and self.end_date < date.today()

    @property
    def is_available(self):
        """Sepete eklenebilir mi? Dört koşulun HEPSİ sağlanmalı:
        ilan aktif, stok var, süresi dolmamış ve ürün satışa açık."""
        return (
            self.status == ListingStatus.ACTIVE
            and self.stock_quantity > 0
            and not self.is_expired
            and self.product is not None
            and self.product.is_active
        )

    @property
    def status_label(self):
        if self.status == ListingStatus.ACTIVE and self.is_expired:
            return "Süresi doldu"
        if self.status == ListingStatus.ACTIVE and self.product is not None and not self.product.is_active:
            return "Ürün satışa kapalı"
        return ListingStatus.LABELS.get(self.status, self.status)

    @property
    def producer(self):
        return self.product.producer

    def __repr__(self):
        return f"<Listing {self.title} {self.price} TL>"
