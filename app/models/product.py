"""Kategori ve ürün modelleri (categories, products tabloları)."""
from app.extensions import db
from app.models.base import BaseModel


class Unit:
    """Satış birimleri."""

    KG = "kg"
    PIECE = "adet"
    CRATE = "kasa"
    BUNCH = "demet"
    LITER = "litre"

    ALL = (KG, PIECE, CRATE, BUNCH, LITER)


class Category(BaseModel):
    __tablename__ = "categories"

    name = db.Column(db.String(60), nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)  # URL için: "kuru-meyve"
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"))

    # Kendine bağlı ilişki: Sebze (üst) -> Domates, Biber (alt)
    parent = db.relationship("Category", remote_side="Category.id", back_populates="children")
    children = db.relationship("Category", back_populates="parent")

    products = db.relationship("Product", back_populates="category")
    market_prices = db.relationship("MarketPrice", back_populates="category")

    def __repr__(self):
        return f"<Category {self.name}>"


class Product(BaseModel):
    """Üreticinin kataloğundaki ürün tanımı. Fiyat ve stok ilanda (Listing) tutulur."""

    __tablename__ = "products"

    producer_id = db.Column(
        db.Integer, db.ForeignKey("producer_profiles.id"), nullable=False, index=True
    )
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(10), default=Unit.KG, nullable=False)
    description = db.Column(db.Text)
    is_organic = db.Column(db.Boolean, default=False, nullable=False)
    image_path = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # --- İlişkiler ---
    producer = db.relationship("ProducerProfile", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    listings = db.relationship("Listing", back_populates="product", cascade="all, delete-orphan")
    predictions = db.relationship(
        "PricePrediction", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Product {self.name}>"
