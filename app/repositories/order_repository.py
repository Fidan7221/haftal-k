"""Sipariş sorguları (Hafta 7)."""
from sqlalchemy import func

from app.extensions import db
from app.models import Order, OrderItem, OrderStatus
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
    @staticmethod
    def get_summary_stats():
        return {}
