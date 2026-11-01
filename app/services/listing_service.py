"""İlan (satış ilanı) iş mantığı (Hafta 7).

Ürün (Product) = üreticinin deposundaki mal. İlan (Listing) = o malın satışa
çıkarılan kısmı + fiyatı. Bir ürünün aynı anda birden fazla ilanı olabilir
(ör. "1. kalite domates 30 TL", "salçalık domates 15 TL").

İŞ KURALLARI:
1. Üretici yalnızca KENDİ ürününe ilan açabilir, yalnızca kendi ilanını değiştirir.
2. Arşivlenmiş (satışa kapalı) ürüne ilan açılmaz.
3. Fiyat ve miktar sıfırdan büyük olmalı; en az sipariş miktarı stoktan büyük olamaz.
4. Bir ürünün açık ilanlarındaki toplam miktar depodaki stoğu AŞAMAZ
   (olmayan malı satmayı engeller).
5. Adet/kasa/demet ile satılan üründe miktar tam sayı olmalı.
6. Bitiş tarihi geçmişte olamaz.
7. Siparişe girmiş ilan silinmez, kapatılır (geçmiş siparişler ilana bağlıdır).
"""
from datetime import date
from decimal import Decimal

from flask import current_app

from app.models import Listing, ListingStatus, Unit
from app.repositories.cart_repository import CartRepository
from app.repositories.listing_repository import ListingRepository
from app.repositories.product_repository import ProductRepository
from app.services.errors import ServiceError

# Bu birimlerde 2,5 adet satılamaz
WHOLE_NUMBER_UNITS = (Unit.PIECE, Unit.CRATE, Unit.BUNCH)


def is_whole(value):
    return Decimal(value) == Decimal(value).to_integral_value()


def check_unit_quantity(unit, quantity, field="quantity"):
    """Kural 5: adet/kasa/demet için kesirli miktarı reddeder."""
    if unit in WHOLE_NUMBER_UNITS and not is_whole(quantity):
        raise ServiceError(f"Bu ürün '{unit}' ile satılıyor; miktar tam sayı olmalı.", field=field)


# --- Sorgular ---------------------------------------------------------------

def public_listings(search=None, category_id=None, page=1):
    per_page = current_app.config.get("ITEMS_PER_PAGE", 12)
    search = (search or "").strip() or None
    return ListingRepository.paginate_public(search, category_id, page, per_page)


def latest_listings(limit=8):
    return ListingRepository.latest_public(limit)


def get_listing(listing_id):
    return ListingRepository.get_by_id(listing_id)


def get_owned_listing(profile, listing_id):
    """İlan bu üreticiye ait değilse None döner; rota 404 gösterir."""
    return ListingRepository.get_for_producer(listing_id, profile.id)


def producer_listings(profile):
    return ListingRepository.list_for_producer(profile.id)


def listable_products(profile):
    """İlan formundaki ürün listesi: yalnızca bu üreticinin satışa açık ürünleri."""
    return [p for p in profile.products if p.is_active]


def free_stock(product, exclude_listing=None):
    """Depoda henüz hiçbir ilana ayrılmamış miktar."""
    used = ListingRepository.open_stock_for_product(
        product.id, exclude_listing.id if exclude_listing else None)
    return product.stock_quantity - used


# --- Doğrulama ----------------------------------------------------------------

def _validate(product, price, stock_quantity, min_order_quantity, end_date, listing=None):
    if price is None or price <= 0:
        raise ServiceError("Fiyat sıfırdan büyük olmalı.", field="price")
    if stock_quantity is None or stock_quantity <= 0:
        raise ServiceError("Satışa ayrılan miktar sıfırdan büyük olmalı.", field="stock_quantity")
    if min_order_quantity is None or min_order_quantity <= 0:
        raise ServiceError("En az sipariş miktarı sıfırdan büyük olmalı.", field="min_order_quantity")
    if min_order_quantity > stock_quantity:
        raise ServiceError("En az sipariş miktarı, satışa ayrılan miktardan büyük olamaz.",
                           field="min_order_quantity")
    if end_date is not None and end_date < date.today():
        raise ServiceError("Bitiş tarihi geçmişte olamaz.", field="end_date")

    check_unit_quantity(product.unit, stock_quantity, field="stock_quantity")
    check_unit_quantity(product.unit, min_order_quantity, field="min_order_quantity")

    available = free_stock(product, exclude_listing=listing)
    if stock_quantity > available:
        raise ServiceError(
            f"Depoda ilana ayrılabilecek en fazla {available.normalize():f} {product.unit} var. "
            "Önce ürün stoğunu artırın.", field="stock_quantity")


# --- Ekle / güncelle / kapat / sil ------------------------------------------------

def create_listing(profile, product_id, title, price, stock_quantity,
                   min_order_quantity=Decimal("1"), end_date=None):
    product = ProductRepository.get_for_producer(product_id, profile.id)  # Kural 1
    if product is None:
        raise ServiceError("Geçerli bir ürününüzü seçin.", field="product_id")
    if not product.is_active:                                              # Kural 2
        raise ServiceError("Satışa kapalı (arşivlenmiş) ürüne ilan açılamaz.", field="product_id")

    _validate(product, price, stock_quantity, min_order_quantity, end_date)

    listing = Listing(
        product=product,
        title=(title or "").strip() or product.name,
        price=price,
        stock_quantity=stock_quantity,
        min_order_quantity=min_order_quantity,
        end_date=end_date,
        status=ListingStatus.ACTIVE,
    )
    ListingRepository.add(listing)
    ListingRepository.commit()
    return listing


def update_listing(listing, title, price, stock_quantity, min_order_quantity, end_date=None):
    """Ürün değiştirilemez; fiyat değişikliği eski siparişleri ETKİLEMEZ
    (sipariş kalemindeki unit_price sipariş anında dondurulur)."""
    _validate(listing.product, price, stock_quantity, min_order_quantity, end_date, listing=listing)

    listing.title = (title or "").strip() or listing.product.name
    listing.price = price
    listing.stock_quantity = stock_quantity
    listing.min_order_quantity = min_order_quantity
    listing.end_date = end_date
    if listing.status == ListingStatus.SOLD_OUT:
        listing.status = ListingStatus.ACTIVE  # stok eklendi, tekrar satışa çıkar
    ListingRepository.commit()
    return listing


def close_listing(listing):
    listing.status = ListingStatus.CLOSED
    ListingRepository.commit()
    return listing


def reopen_listing(listing):
    if not listing.product.is_active:
        raise ServiceError("Ürün satışa kapalı olduğu için ilan açılamaz.")
    if listing.is_expired:
        raise ServiceError("İlanın bitiş tarihi geçmiş; önce düzenleyip tarihi değiştirin.")
    # Kapalı ilanın stoğu tekrar "ayrılmış" sayılacağı için depo kontrolü yeniden yapılır
    if listing.stock_quantity > free_stock(listing.product, exclude_listing=listing):
        raise ServiceError("Depoda bu ilan için yeterli stok yok; önce ilan miktarını azaltın.")
    listing.status = ListingStatus.ACTIVE if listing.stock_quantity > 0 else ListingStatus.SOLD_OUT
    ListingRepository.commit()
    return listing


def delete_listing(listing):
    """Siparişe girmiş ilan kapatılır, girmemiş ilan sepetlerden de çıkarılarak silinir."""
    if ListingRepository.has_orders(listing.id):
        listing.status = ListingStatus.CLOSED
        ListingRepository.commit()
        return "closed"
    CartRepository.delete_items_for_listing(listing.id)  # ilişkili kayıtlar önce
    ListingRepository.delete(listing)
    ListingRepository.commit()
    return "deleted"
