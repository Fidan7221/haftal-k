"""Sipariş iş mantığı ve durum yönetimi (Hafta 7).

SİPARİŞ YAŞAM DÖNGÜSÜ (durum makinesi):

    pending (ödeme bekleniyor) ──öde──> paid (ödendi) ──kargola──> shipped (kargoda) ──teslim──> delivered
        │                                  │
        └───────────iptal──────────────────┴──> cancelled (iptal)

- Geçişlerin TAMAMI aşağıdaki TRANSITIONS tablosunda. Tabloda olmayan geçiş
  (ör. delivered -> pending, cancelled -> paid) servis tarafından REDDEDİLİR.
- Her geçişi kimin yapabileceği de tabloda: müşteri, üretici veya yönetici.
- delivered ve cancelled SON durumlardır; buradan başka duruma geçilmez.

SEPETTEN SİPARİŞE GEÇİŞ (checkout) tek bir işlem (transaction) içinde yapılır:
  1) Her sepet kalemi yeniden doğrulanır (ilan hâlâ satışta mı, stok yetiyor mu?)
  2) Sepet ÜRETİCİYE GÖRE bölünür: her üretici için ayrı sipariş oluşur.
     Böylece her siparişin tek bir sahibi (üreticisi) olur, kargo durumu ayrı yönetilir.
  3) Sipariş kalemine o anki fiyat KOPYALANIR (unit_price); ilan fiyatı sonra değişse
     de sipariş tutarı değişmez.
  4) İlan stoğu ve depo (ürün) stoğu koşullu UPDATE ile düşülür.
  5) Sepet boşaltılır.
  Bir adım bile başarısız olursa rollback: ne sipariş oluşur ne stok düşer.
"""
from decimal import Decimal

from app.models import ListingStatus, Order, OrderItem, OrderStatus, PaymentStatus
from app.repositories.cart_repository import CartRepository
from app.repositories.listing_repository import ListingRepository
from app.repositories.order_repository import OrderRepository
from app.services import notification_service, payment_service
from app.services.cart_service import item_problem
from app.services.errors import ServiceError

CUSTOMER, PRODUCER, ADMIN = "customer", "producer", "admin"

# {mevcut durum: {yeni durum: {bu geçişi yapabilecek roller}}}
TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.PAID: {CUSTOMER},                         # yalnızca ödeme formuyla (payment_service)
        OrderStatus.CANCELLED: {CUSTOMER, PRODUCER, ADMIN},
    },
    OrderStatus.PAID: {
        OrderStatus.SHIPPED: {PRODUCER, ADMIN},               # üretici kargoya verir
        OrderStatus.CANCELLED: {CUSTOMER, PRODUCER, ADMIN},   # kargodan önce iptal -> iade
    },
    OrderStatus.SHIPPED: {
        OrderStatus.DELIVERED: {CUSTOMER, PRODUCER, ADMIN},   # müşteri teslim aldığını onaylar
    },
    OrderStatus.DELIVERED: {},  # son durum
    OrderStatus.CANCELLED: {},  # son durum
}

# Düğmelerde görünecek metinler
# Hafta 9: "Öde" artık bir durum düğmesi değil; kart bilgisiyle ödeme formu açılır
# (payment_service.pay_order). Bu yüzden PAID burada yok.
ACTION_LABELS = {
    OrderStatus.SHIPPED: "Kargoya verdim",
    OrderStatus.DELIVERED: "Teslim alındı",
    OrderStatus.CANCELLED: "Siparişi iptal et",
}


# --- Erişim ve yetki ----------------------------------------------------------

def actor_role(user, order):
    """Kullanıcının bu siparişteki rolü; hiçbir ilgisi yoksa None (rota 404 verir)."""
    if user.is_admin:
        return ADMIN
    if order.customer_id == user.id:
        return CUSTOMER
    profile = user.producer_profile
    if profile is not None and order.producer is not None and order.producer.id == profile.id:
        return PRODUCER
    return None


def allowed_actions(user, order):
    """Bu kullanıcının bu siparişte basabileceği düğmeler: [(yeni_durum, etiket), ...]"""
    role = actor_role(user, order)
    return [
        (new_status, ACTION_LABELS[new_status])
        for new_status, roles in TRANSITIONS.get(order.status, {}).items()
        if role in roles and new_status in ACTION_LABELS
    ]


def can_pay(user, order):
    """Ödeme formu bu kullanıcıya bu siparişte gösterilsin mi?"""
    return order.status == OrderStatus.PENDING and actor_role(user, order) == CUSTOMER


def customer_orders(user):
    return OrderRepository.list_for_customer(user.id)


def get_customer_order(user, order_id):
    return OrderRepository.get_for_customer(order_id, user.id)


def producer_orders(profile, status=None):
    return OrderRepository.list_for_producer(profile.id, status)


def get_producer_order(profile, order_id):
    return OrderRepository.get_for_producer(order_id, profile.id)


def waiting_count(profile):
    return OrderRepository.count_waiting_for_producer(profile.id)


# --- Sepetten siparişe ----------------------------------------------------------

def checkout(user, shipping_address, note=None):
    cart = CartRepository.get_by_user(user.id)
    if cart is None or not cart.items:
        raise ServiceError("Sepetiniz boş.")

    shipping_address = (shipping_address or "").strip()
    if len(shipping_address) < 10:
        raise ServiceError("Teslimat adresini eksiksiz yazın (en az 10 karakter).",
                           field="shipping_address")

    # 1) Ön kontrol: sorunlu kalem varsa hiçbir şey yapmadan kullanıcıya göster
    for item in cart.items:
        problem = item_problem(item.listing, item.quantity)
        if problem:
            raise ServiceError(f"'{item.listing.title}': {problem} Lütfen sepetinizi güncelleyin.")

    # 2) Üreticiye göre grupla
    groups = {}
    for item in cart.items:
        groups.setdefault(item.listing.product.producer_id, []).append(item)

    orders = []
    try:
        for producer_id, items in groups.items():
            order = Order(
                customer=user,
                shipping_address=shipping_address,
                note=(note or "").strip() or None,
                status=OrderStatus.PENDING,
                total_amount=Decimal("0"),
            )
            OrderRepository.add(order)
            total = Decimal("0")
            for item in items:
                listing = item.listing
                stock_before = listing.stock_quantity  # Hafta 12: eşik geçişini yakalamak için
                # 4) Stok düş: koşullu UPDATE 0 satır döndürürse stok başkası tarafından alınmış
                if ListingRepository.decrease_stock(listing.id, item.quantity) == 0 or \
                        ListingRepository.decrease_product_stock(listing.product_id, item.quantity) == 0:
                    raise ServiceError(f"'{listing.title}' için stok az önce tükendi. "
                                       "Sepetinizi güncelleyip tekrar deneyin.")
                if listing.stock_quantity <= 0:
                    listing.status = ListingStatus.SOLD_OUT
                notification_service.stock_changed(listing, stock_before, listing.stock_quantity)

                # 3) Fiyatı dondur
                order.items.append(OrderItem(
                    listing=listing,
                    producer_id=producer_id,
                    quantity=item.quantity,
                    unit_price=listing.price,
                ))
                total += item.quantity * listing.price
            order.total_amount = total
            orders.append(order)

        # 5) Sepeti boşalt
        for item in list(cart.items):
            CartRepository.delete(item)

        OrderRepository.commit()  # Hepsi birlikte kalıcı olur
    except Exception:
        OrderRepository.rollback()  # Ya hepsi ya hiçbiri
        raise
    return orders


# --- Durum değiştirme -----------------------------------------------------------

def change_status(user, order, new_status):
    role = actor_role(user, order)
    if role is None:
        raise ServiceError("Bu sipariş üzerinde işlem yetkiniz yok.")

    possible = TRANSITIONS.get(order.status, {})
    if new_status not in possible:
        raise ServiceError(
            f"'{order.status_label}' durumundaki sipariş "
            f"'{OrderStatus.LABELS.get(new_status, new_status)}' durumuna geçemez.")
    if role not in possible[new_status]:
        raise ServiceError("Bu işlemi yapma yetkiniz yok.")
    if new_status == OrderStatus.PAID:
        # Hafta 9: Ödeme durumu elle seçilemez; para gerçekten alınınca payment_service yapar
        raise ServiceError("Ödeme yalnızca ödeme formundan yapılabilir.")

    try:
        if new_status == OrderStatus.CANCELLED:
            # Önce iade (harici API). Başarısızsa ServiceError -> rollback, sipariş iptal olmaz
            was_paid = order.payment is not None and order.payment.status == PaymentStatus.SUCCESS
            payment_service.refund_payment(order.payment)
            _restore_stock(order)
            notification_service.order_cancelled(order, role, refunded=was_paid)
        elif new_status == OrderStatus.SHIPPED:
            notification_service.order_shipped(order)
        elif new_status == OrderStatus.DELIVERED:
            notification_service.order_delivered(order)
        order.status = new_status
        OrderRepository.commit()  # durum ve bildirimler birlikte kalıcı olur
    except Exception:
        OrderRepository.rollback()
        raise
    return order


def _restore_stock(order):
    """İptalde düşülen stok ilana ve depoya geri eklenir (ilişkili kayıtları yönetmek)."""
    for item in order.items:
        listing = item.listing
        ListingRepository.increase_stock(listing.id, item.quantity)
        ListingRepository.increase_product_stock(listing.product_id, item.quantity)
        if listing.status == ListingStatus.SOLD_OUT and not listing.is_expired:
            listing.status = ListingStatus.ACTIVE
