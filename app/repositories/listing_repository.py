"""İlan sorguları (Hafta 7).

Not: Sahiplik kontrolü sorgunun İÇİNDE yapılır (Listing -> Product -> producer_id).
Başka üreticinin ilanı istenirse None döner, rota 404 gösterir.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, update

from app.extensions import db
from app.models import Category, Listing, ListingStatus, OrderItem, Product
from app.repositories.base_repository import BaseRepository


class ListingRepository(BaseRepository):
    model = Listing

    # --- Herkese açık vitrin --------------------------------------------------

    @staticmethod
    def _public_query():
        """Satışta olan ilanlar: aktif, stoklu, süresi dolmamış ve ürünü satışa açık."""
        today = date.today()
        return (
            db.select(Listing)
            .join(Product, Listing.product_id == Product.id)
            .where(
                Listing.status == ListingStatus.ACTIVE,
                Listing.stock_quantity > 0,
                or_(Listing.end_date.is_(None), Listing.end_date >= today),
                Product.is_active.is_(True),
            )
        )

    @staticmethod
    def paginate_public(search=None, category_id=None, page=1, per_page=12):
        stmt = ListingRepository._public_query()
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Listing.title.ilike(like), Product.name.ilike(like)))
        if category_id:
            # Üst kategori seçilirse alt kategorilerdeki ilanlar da gelsin
            child_ids = db.select(Category.id).where(Category.parent_id == category_id)
            stmt = stmt.where(or_(Product.category_id == category_id,
                                  Product.category_id.in_(child_ids)))
        stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def latest_public(limit=8):
        stmt = ListingRepository._public_query().order_by(
            Listing.created_at.desc(), Listing.id.desc()).limit(limit)
        return db.session.execute(stmt).scalars().all()

    # --- Üretici --------------------------------------------------------------

    @staticmethod
    def get_for_producer(listing_id, producer_id):
        return db.session.execute(
            db.select(Listing).join(Product)
            .where(Listing.id == listing_id, Product.producer_id == producer_id)
        ).scalar_one_or_none()

    @staticmethod
    def list_for_producer(producer_id):
        return db.session.execute(
            db.select(Listing).join(Product)
            .where(Product.producer_id == producer_id)
            .order_by(Listing.created_at.desc(), Listing.id.desc())
        ).scalars().all()

    @staticmethod
    def open_stock_for_product(product_id, exclude_listing_id=None):
        """Ürünün açık (kapatılmamış) ilanlarında satışa ayrılmış toplam miktar."""
        stmt = db.select(func.coalesce(func.sum(Listing.stock_quantity), 0)).where(
            Listing.product_id == product_id, Listing.status != ListingStatus.CLOSED
        )
        if exclude_listing_id is not None:
            stmt = stmt.where(Listing.id != exclude_listing_id)
        return Decimal(db.session.execute(stmt).scalar())

    @staticmethod
    def has_orders(listing_id):
        count = db.session.execute(
            db.select(func.count(OrderItem.id)).where(OrderItem.listing_id == listing_id)
        ).scalar()
        return count > 0

    # --- Stok hareketleri (sipariş ve iptal) ----------------------------------

    @staticmethod
    def decrease_stock(listing_id, quantity):
        """Koşullu UPDATE: stok yeterliyse düşer, değilse hiçbir satır değişmez.

        UPDATE listings SET stock_quantity = stock_quantity - :q
         WHERE id = :id AND stock_quantity >= :q

        Kontrol ve düşme TEK SQL cümlesinde olduğu için aynı anda iki müşteri son
        ürünü almaya çalışsa bile stok eksiye düşmez (yarış durumu / race condition).
        Dönen değer: güncellenen satır sayısı (1 = başarılı, 0 = stok yetersiz).
        """
        result = db.session.execute(
            update(Listing)
            .where(Listing.id == listing_id, Listing.stock_quantity >= quantity)
            .values(stock_quantity=Listing.stock_quantity - quantity)
        )
        return result.rowcount

    @staticmethod
    def increase_stock(listing_id, quantity):
        db.session.execute(
            update(Listing).where(Listing.id == listing_id)
            .values(stock_quantity=Listing.stock_quantity + quantity)
        )

    @staticmethod
    def decrease_product_stock(product_id, quantity):
        """Depodaki ürün stoğunu da aynı koşullu yöntemle düşürür."""
        result = db.session.execute(
            update(Product)
            .where(Product.id == product_id, Product.stock_quantity >= quantity)
            .values(stock_quantity=Product.stock_quantity - quantity)
        )
        return result.rowcount

    @staticmethod
    def increase_product_stock(product_id, quantity):
        db.session.execute(
            update(Product).where(Product.id == product_id)
            .values(stock_quantity=Product.stock_quantity + quantity)
        )
