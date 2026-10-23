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

    @property
    def is_available(self):
        return self.status == ListingStatus.ACTIVE and self.stock_quantity > 0

    def __repr__(self):
        return f"<Listing {self.title} {self.price} TL>"
