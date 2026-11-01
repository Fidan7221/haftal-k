"""Sipariş sorguları (Hafta 7)."""
from sqlalchemy import func

from app.extensions import db
from app.models import Listing, ListingStatus, Order, OrderItem, OrderStatus, Product, Role, User
from app.repositories.base_repository import BaseRepository


class OrderRepository(BaseRepository):
    model = Order

    @staticmethod
    def list_for_customer(customer_id):
        return db.session.execute(
            db.select(Order).filter_by(customer_id=customer_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
        ).scalars().all()

    @staticmethod
    def get_for_customer(order_id, customer_id):
        return db.session.execute(
            db.select(Order).filter_by(id=order_id, customer_id=customer_id)
        ).scalar_one_or_none()

    @staticmethod
    def _producer_order_ids(producer_id):
        return db.select(OrderItem.order_id).where(OrderItem.producer_id == producer_id)

    @staticmethod
    def list_for_producer(producer_id, status=None):
        stmt = db.select(Order).where(Order.id.in_(OrderRepository._producer_order_ids(producer_id)))
        if status:
            stmt = stmt.where(Order.status == status)
        return db.session.execute(
            stmt.order_by(Order.created_at.desc(), Order.id.desc())
        ).scalars().all()

    @staticmethod
    def get_for_producer(order_id, producer_id):
        return db.session.execute(
            db.select(Order).where(
                Order.id == order_id,
                Order.id.in_(OrderRepository._producer_order_ids(producer_id)),
            )
        ).scalar_one_or_none()

    @staticmethod
    def count_waiting_for_producer(producer_id):
        """Üreticinin kargolaması gereken (ödenmiş) sipariş sayısı."""
        return db.session.execute(
            db.select(func.count(Order.id)).where(
                Order.status == OrderStatus.PAID,
                Order.id.in_(OrderRepository._producer_order_ids(producer_id)),
            )
        ).scalar()


class StatsRepository:
    """Yönetici paneli özet sayıları (Hafta 8: modüllerin uçtan uca bağlı olduğunu gösterir).

    Her sayı farklı bir modülün tablosundan gelir:
    users/roles (Hafta 5) · products (Hafta 6) · listings, orders (Hafta 7)
    """

    @staticmethod
    def get_summary_stats():
        def scalar(stmt):
            return db.session.execute(stmt).scalar() or 0

        # SELECT roles.name, COUNT(users.id) FROM users JOIN roles ... GROUP BY roles.name
        users_by_role = dict(db.session.execute(
            db.select(Role.name, func.count(User.id)).join(User.role).group_by(Role.name)
        ).all())
        orders_by_status = dict(db.session.execute(
            db.select(Order.status, func.count(Order.id)).group_by(Order.status)
        ).all())
        return {
            "users_by_role": users_by_role,
            "user_total": sum(users_by_role.values()),
            "product_total": scalar(db.select(func.count(Product.id))),
            "active_listing_total": scalar(
                db.select(func.count(Listing.id)).where(Listing.status == ListingStatus.ACTIVE)),
            "orders_by_status": orders_by_status,
            "order_total": sum(orders_by_status.values()),
            # Ciro: yalnızca ödemesi alınmış (ödendi/kargoda/teslim) siparişler; iptal ve bekleyen sayılmaz
            "revenue": scalar(db.select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.status.in_((OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED)))),
        }

    @staticmethod
    def recent_orders(limit=10, status=None):
        stmt = db.select(Order)
        if status:
            stmt = stmt.where(Order.status == status)
        return db.session.execute(
            stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
        ).scalars().all()
