"""Değerlendirme sorguları (Hafta 11)."""
from datetime import datetime

from sqlalchemy import func

from app.extensions import db
from app.models import Listing, OrderItem, ProducerProfile, Review
from app.repositories.base_repository import BaseRepository


class ReviewRepository(BaseRepository):
    model = Review

    @staticmethod
    def visible_for_producer(producer_id):
        """İtibar hesabına giren yorumlar: yalnızca görünür (yöneticinin gizlemediği) olanlar."""
        return db.session.execute(
            db.select(Review).filter_by(producer_id=producer_id, is_visible=True)
        ).scalars().all()

    @staticmethod
    def platform_average():
        """Tüm görünür yorumların ortalaması (Bayes ortalamasındaki "önsel" değer); yoksa None."""
        return db.session.execute(
            db.select(func.avg(Review.rating)).filter_by(is_visible=True)
        ).scalar()

    @staticmethod
    def count_by_customer_since(customer_id, since: datetime):
        return db.session.execute(
            db.select(func.count(Review.id)).where(Review.customer_id == customer_id,
                                                   Review.created_at >= since)
        ).scalar()

    @staticmethod
    def _for_product(product_id):
        return (db.select(Review)
                .join(OrderItem, Review.order_item_id == OrderItem.id)
                .join(Listing, OrderItem.listing_id == Listing.id)
                .where(Listing.product_id == product_id, Review.is_visible.is_(True)))

    @classmethod
    def latest_for_product(cls, product_id, limit=10):
        return db.session.execute(
            cls._for_product(product_id).order_by(Review.created_at.desc()).limit(limit)
        ).scalars().all()

    @staticmethod
    def product_summary(product_id):
        """(ortalama, sayı) — ürünün görünür yorumları."""
        avg, count = db.session.execute(
            db.select(func.avg(Review.rating), func.count(Review.id))
            .join(OrderItem, Review.order_item_id == OrderItem.id)
            .join(Listing, OrderItem.listing_id == Listing.id)
            .where(Listing.product_id == product_id, Review.is_visible.is_(True))
        ).one()
        return (float(avg) if avg is not None else None), count

    @staticmethod
    def producers_with_reviews():
        return db.session.execute(
            db.select(ProducerProfile).where(
                ProducerProfile.id.in_(db.select(Review.producer_id).distinct()))
        ).scalars().all()

    @staticmethod
    def list_for_producer(producer_id):
        return db.session.execute(
            db.select(Review).filter_by(producer_id=producer_id).order_by(Review.created_at.desc())
        ).scalars().all()

    @staticmethod
    def list_all(limit=200, only_hidden=False):
        stmt = db.select(Review).order_by(Review.created_at.desc()).limit(limit)
        if only_hidden:
            stmt = stmt.where(Review.is_visible.is_(False))
        return db.session.execute(stmt).scalars().all()
