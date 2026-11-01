"""Sepet sorguları (Hafta 7)."""
from app.extensions import db
from app.models import Cart, CartItem
from app.repositories.base_repository import BaseRepository


class CartRepository(BaseRepository):
    model = Cart

    @staticmethod
    def get_by_user(user_id):
        return db.session.execute(
            db.select(Cart).filter_by(user_id=user_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_item(cart_id, listing_id):
        return db.session.execute(
            db.select(CartItem).filter_by(cart_id=cart_id, listing_id=listing_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_item_for_user(item_id, user_id):
        """Sahiplik kontrolü: kalem bu kullanıcının sepetinde değilse None döner."""
        return db.session.execute(
            db.select(CartItem).join(Cart)
            .where(CartItem.id == item_id, Cart.user_id == user_id)
        ).scalar_one_or_none()

    @staticmethod
    def delete_items_for_listing(listing_id):
        """İlan silinirken onu içeren sepet kalemleri de silinir (ilişkili kayıt yönetimi)."""
        db.session.execute(db.delete(CartItem).where(CartItem.listing_id == listing_id))
