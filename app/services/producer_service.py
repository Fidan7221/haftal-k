"""Üretici profili ve ürün yönetimi iş mantığı (Hafta 6).

Önemli kurallar:
- Üretici yalnızca KENDİ ürünlerini görebilir ve değiştirebilir (sahiplik kontrolü).
- Stok negatif olamaz.
- Siparişe girmiş bir ürün silinmez, arşivlenir (is_active=False). Çünkü geçmiş
  siparişler ve raporlar o ürüne bağlıdır; silmek veri bütünlüğünü bozar.
"""
from decimal import Decimal

from flask import current_app

from app.models import Product, Unit
from app.repositories.product_repository import CategoryRepository, ProductRepository
from app.services.errors import ServiceError
from app.utils.uploads import delete_product_image, is_real_image, save_product_image

LOW_STOCK_THRESHOLD = Decimal("5")


def _upload_root():
    return current_app.config["UPLOAD_FOLDER"]


# --- Profil --------------------------------------------------------------

def update_profile(user, full_name, phone, city, farm_name, region, description, tax_number):
    profile = user.producer_profile
    if profile is None:
        raise ServiceError("Üretici profili bulunamadı.")

    user.full_name = full_name.strip()
    user.phone = (phone or "").strip() or None
    user.city = (city or "").strip() or None

    profile.farm_name = farm_name.strip()
    profile.region = region.strip()
    profile.description = (description or "").strip() or None
    profile.tax_number = (tax_number or "").strip() or None

    ProductRepository.commit()
    return profile


# --- Ürün sorguları --------------------------------------------------------

def get_owned_product(profile, product_id):
    """Ürün bu üreticiye ait değilse None döner; rota 404 gösterir."""
    return ProductRepository.get_for_producer(product_id, profile.id)


def list_products(profile, search=None, category_id=None, page=1):
    per_page = current_app.config.get("ITEMS_PER_PAGE", 12)
    search = (search or "").strip() or None
    return ProductRepository.paginate_for_producer(profile.id, search, category_id, page, per_page)


def dashboard_data(profile):
    return {
        "stats": ProductRepository.stats_for_producer(profile.id, LOW_STOCK_THRESHOLD),
        "recent": ProductRepository.recent_for_producer(profile.id),
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
    }


# --- Ürün ekleme / güncelleme / silme -------------------------------------

def _validate_product(category_id, unit, stock_quantity):
    category = CategoryRepository.get_by_id(category_id)
    if category is None:
        raise ServiceError("Geçerli bir kategori seçin.", field="category_id")
    if unit not in Unit.ALL:
        raise ServiceError("Geçersiz birim.", field="unit")
    if stock_quantity is None or stock_quantity < 0:
        raise ServiceError("Stok negatif olamaz.", field="stock_quantity")
    return category


def _handle_image(image_file):
    """Yeni görsel geldiyse doğrular ve kaydeder; gelmediyse None döner."""
    if not image_file:
        return None
    if not is_real_image(image_file):
        raise ServiceError("Yüklenen dosya geçerli bir resim değil.", field="image")
    return save_product_image(image_file, _upload_root())


def create_product(profile, category_id, name, unit, stock_quantity,
                   description=None, is_organic=False, is_active=True, image_file=None):
    category = _validate_product(category_id, unit, stock_quantity)
    image_path = _handle_image(image_file)

    product = Product(
        producer=profile,
        category=category,
        name=name.strip(),
        unit=unit,
        stock_quantity=stock_quantity,
        description=(description or "").strip() or None,
        is_organic=bool(is_organic),
        is_active=bool(is_active),
        image_path=image_path,
    )
    ProductRepository.add(product)
    try:
        ProductRepository.commit()
    except Exception:
        # Veri tabanı kaydı başarısız olursa diske yazılan görsel öksüz kalmasın
        ProductRepository.rollback()
        delete_product_image(image_path, _upload_root())
        raise
    return product


def update_product(product, category_id, name, unit, stock_quantity,
                   description=None, is_organic=False, is_active=True,
                   image_file=None, remove_image=False):
    category = _validate_product(category_id, unit, stock_quantity)
    new_image = _handle_image(image_file)
    old_image = product.image_path

    product.category = category
    product.name = name.strip()
    product.unit = unit
    product.stock_quantity = stock_quantity
    product.description = (description or "").strip() or None
    product.is_organic = bool(is_organic)
    product.is_active = bool(is_active)

    if new_image:
        product.image_path = new_image
    elif remove_image:
        product.image_path = None

    ProductRepository.commit()

    # Eski görsel yalnızca kayıt başarılı olduktan sonra silinir
    if old_image and old_image != product.image_path:
        delete_product_image(old_image, _upload_root())
    return product


def update_stock(product, new_quantity):
    """Yalnızca stok miktarını günceller (ürün listesindeki hızlı stok formu).

    Kural formda da var; servis yine de kontrol eder, çünkü servis formdan
    bağımsız olarak da (CLI, test, ileride API) çağrılabilir.
    """
    if new_quantity is None or new_quantity < 0:
        raise ServiceError("Stok negatif olamaz.", field="quantity")
    product.stock_quantity = new_quantity
    ProductRepository.commit()
    return product


def delete_product(product):
    """Siparişi olan ürünü arşivler, olmayanı tamamen siler. Sonucu metin olarak döndürür."""
    if ProductRepository.has_orders(product.id):
        product.is_active = False
        ProductRepository.commit()
        return "archived"

    image_path = product.image_path
    ProductRepository.delete(product)  # İlanlar cascade ile birlikte silinir
    ProductRepository.commit()
    delete_product_image(image_path, _upload_root())
    return "deleted"
