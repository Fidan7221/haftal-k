"""Sepet iş mantığı (Hafta 7).

İŞ KURALLARI:
1. Sepeti yalnızca müşteri kullanır (rota @role_required(CUSTOMER) ile korunur).
2. Yalnızca satışta olan ilan sepete eklenir (aktif, stoklu, süresi dolmamış).
3. Miktar >= ilanın en az sipariş miktarı ve <= ilan stoğu olmalı.
4. Aynı ilan ikinci kez eklenirse yeni satır açılmaz, miktar artırılır
   (veri tabanında da UNIQUE(cart_id, listing_id) kısıtı var).
5. Sepete eklemek stok DÜŞMEZ. Stok, sipariş oluştuğu anda düşer; bu yüzden
   ödeme adımında her kalem yeniden kontrol edilir (bkz. order_service.checkout).
6. Kullanıcı yalnızca KENDİ sepet kalemini değiştirebilir/silebilir (sahiplik).
"""
from decimal import Decimal

from app.models import Cart, CartItem
from app.repositories.cart_repository import CartRepository
from app.services.errors import ServiceError
from app.services.listing_service import check_unit_quantity


def get_cart(user):
    return CartRepository.get_by_user(user.id)


def get_or_create_cart(user):
    cart = CartRepository.get_by_user(user.id)
    if cart is None:
        cart = Cart(user=user)
        CartRepository.add(cart)
    return cart


def item_problem(listing, quantity):
    """Kalemde sorun varsa açıklamasını, yoksa None döndürür (Kural 2-3)."""
    if not listing.is_available:
        return "Bu ilan artık satışta değil."
    if quantity < listing.min_order_quantity:
        return f"En az {listing.min_order_quantity.normalize():f} {listing.product.unit} sipariş verilebilir."
    if quantity > listing.stock_quantity:
        return f"Stokta yalnızca {listing.stock_quantity.normalize():f} {listing.product.unit} var."
    return None


def _check(listing, quantity):
    if quantity is None or quantity <= 0:
        raise ServiceError("Miktar sıfırdan büyük olmalı.", field="quantity")
    check_unit_quantity(listing.product.unit, quantity)
    problem = item_problem(listing, quantity)
    if problem:
        raise ServiceError(problem, field="quantity")


def add_to_cart(user, listing, quantity):
    if listing.product.producer.user_id == user.id:
        raise ServiceError("Kendi ilanınızı satın alamazsınız.")

    cart = get_or_create_cart(user)
    item = CartRepository.get_item(cart.id, listing.id) if cart.id else None
    new_quantity = (item.quantity if item else Decimal("0")) + quantity  # Kural 4
    _check(listing, new_quantity)

    if item:
        item.quantity = new_quantity
    else:
        item = CartItem(cart=cart, listing=listing, quantity=new_quantity)
        CartRepository.add(item)
    CartRepository.commit()
    return item


def get_owned_item(user, item_id):
    return CartRepository.get_item_for_user(item_id, user.id)


def update_item(item, quantity):
    """Miktar 0 girilirse kalem sepetten çıkarılır."""
    if quantity is not None and quantity == 0:
        return remove_item(item)
    _check(item.listing, quantity)
    item.quantity = quantity
    CartRepository.commit()
    return item


def remove_item(item):
    CartRepository.delete(item)
    CartRepository.commit()


def cart_summary(user):
    """Sepet sayfası için: üreticiye göre gruplanmış kalemler, toplam ve sorunlar."""
    cart = get_cart(user)
    items = list(cart.items) if cart else []
    groups = {}
    problems = {}
    for item in items:
        groups.setdefault(item.listing.product.producer, []).append(item)
        problem = item_problem(item.listing, item.quantity)
        if problem:
            problems[item.id] = problem
    total = sum((item.subtotal for item in items), Decimal("0"))
    return {"items": items, "groups": groups, "problems": problems, "total": total}


def item_count(user):
    cart = get_cart(user)
    return cart.item_count if cart else 0
