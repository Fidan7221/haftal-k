"""Hafta 8 — ENTEGRASYON TESTLERİ (ara sürüm v0.8.0).

Birim testi tek bir fonksiyonu tek başına dener. ENTEGRASYON TESTİ ise birden fazla
modülün BİRLİKTE doğru çalıştığını dener: burada her test gerçek bir kullanıcı gibi
HTTP istekleri gönderir (form -> rota -> servis -> repository -> veri tabanı) ve sonucu
hem sayfada hem veri tabanında kontrol eder.

Bölümler:
  1) Uçtan uca senaryo: kayıt -> ürün -> ilan -> sepet -> sipariş -> ödeme -> kargo -> teslim
  2) Çok üreticili sepet + iptal (stok iade zinciri)
  3) Duman testi (smoke test): her rol için tüm sayfalar açılıyor mu? (500 hatası yok)
  4) REGRESYON testleri: Hafta 8'de düzeltilen hatalar bir daha geri gelmesin

Çalıştırma: python -m pytest -v tests/test_integration.py
"""
from decimal import Decimal

from sqlalchemy import text

from app import __version__
from app.extensions import db
from app.models import (
    CartItem, Category, Listing, ListingStatus, Order, OrderStatus, PaymentStatus, Product,
)
from app.services.auth_service import create_admin_user

PASSWORD = "Parola123"


# --- Yardımcılar: gerçek kullanıcı gibi form gönderirler ------------------------------

def register(client, email, role, full_name="Deneme Kullanıcı", farm_name="Deneme Çiftliği"):
    data = {"role": role, "full_name": full_name, "email": email, "password": PASSWORD,
            "confirm_password": PASSWORD, "accept_terms": "y"}
    if role == "producer":
        data.update(farm_name=farm_name, region="Bingöl / Merkez")
    return client.post("/auth/register", data=data, follow_redirects=True)


def login(client, email, password=PASSWORD):
    return client.post("/auth/login", data={"email": email, "password": password},
                       follow_redirects=True)


def logout(client):
    client.post("/auth/logout")


def add_product_via_form(client, name="Salkım Domates", stock="100", unit="kg"):
    category = Category.query.filter_by(slug="domates").first()
    client.post("/uretici/urunler/yeni", data={
        "name": name, "category_id": str(category.id), "unit": unit, "stock_quantity": stock,
        "description": "Sentetik test ürünü", "is_active": "y",
    }, follow_redirects=True)
    return Product.query.filter_by(name=name).one()


def open_listing_via_form(client, product, price="30", stock="50", min_order="1", title=None):
    client.post("/uretici/ilanlar/yeni", data={
        "product_id": str(product.id), "title": title or product.name, "price": price,
        "stock_quantity": stock, "min_order_quantity": min_order, "end_date": "",
    }, follow_redirects=True)
    return Listing.query.filter_by(product_id=product.id).order_by(Listing.id.desc()).first()


def producer_with_listing(client, email, farm, product_name, price="30", stock="50", product_stock="100"):
    register(client, email, "producer", farm_name=farm)
    login(client, email)
    product = add_product_via_form(client, name=product_name, stock=product_stock)
    listing = open_listing_via_form(client, product, price=price, stock=stock)
    logout(client)
    return product, listing


def set_status(client, order_id, new_status):
    return client.post(f"/siparis/{order_id}/durum", data={"new_status": new_status},
                       follow_redirects=True)


ADDRESS = "Yenişehir Mah. Örnek Sok. No:1 Merkez / Bingöl"  # uydurma adres (KVKK)


# --- 1) UÇTAN UCA SENARYO --------------------------------------------------------------

def test_end_to_end_happy_path(client):
    """Vize demosunun aynısı: Kullanıcı + veri tabanı + çekirdek modüller birlikte çalışır."""
    # Üretici: kayıt -> giriş -> ürün (Hafta 6) -> ilan (Hafta 7)
    product, listing = producer_with_listing(client, "uretici@example.com", "Yeşil Vadi",
                                             "Salkım Domates", price="32.50", stock="40")
    assert listing.status == ListingStatus.ACTIVE

    # Ziyaretçi (giriş yapmadan) ilanı vitrinde görür
    html = client.get("/ilanlar").get_data(as_text=True)
    assert "Salkım Domates" in html and "Yeşil Vadi" in html

    # Müşteri: kayıt -> giriş -> sepete ekle -> ödeme sayfası -> sipariş
    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "4"}, follow_redirects=True)
    assert "Salkım Domates" in client.get("/sepet/").get_data(as_text=True)

    page = client.post("/sepet/odeme", data={"shipping_address": ADDRESS, "note": ""},
                       follow_redirects=True)
    assert "Siparişiniz oluşturuldu" in page.get_data(as_text=True)
    order = Order.query.one()
    assert order.status == OrderStatus.PENDING
    assert order.total_amount == Decimal("130.00")          # 4 x 32,50 (fiyat donduruldu)

    # Stok iki yerde de düştü: ilan (satışa ayrılan) ve ürün (depo)
    db.session.refresh(listing)
    db.session.refresh(product)
    assert listing.stock_quantity == Decimal("36")
    assert product.stock_quantity == Decimal("96")

    # Müşteri öder (mock ödeme, Hafta 9'da gerçeği gelecek)
    set_status(client, order.id, OrderStatus.PAID)
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert order.payment.status == PaymentStatus.SUCCESS
    logout(client)

    # Üretici siparişi panelinde görür ve kargoya verir
    login(client, "uretici@example.com")
    assert "1" in client.get("/uretici/panel").get_data(as_text=True)  # bekleyen sipariş rozeti
    assert f"#{order.id}" in client.get("/uretici/siparisler").get_data(as_text=True)
    set_status(client, order.id, OrderStatus.SHIPPED)
    logout(client)

    # Müşteri teslim aldığını onaylar
    login(client, "musteri@example.com")
    set_status(client, order.id, OrderStatus.DELIVERED)
    db.session.refresh(order)
    assert order.status == OrderStatus.DELIVERED
    logout(client)

    # Yönetici panelinde tüm modüllerden gelen sayılar görünür
    create_admin_user("Yönetici", "admin@example.com", "Yonetici123")
    login(client, "admin@example.com", "Yonetici123")
    html = client.get("/yonetici/panel").get_data(as_text=True)
    assert 'data-test="user-total">3<' in html       # üretici + müşteri + yönetici
    assert 'data-test="order-total">1<' in html
    assert "130,00" in html                           # ciro (teslim edilen sipariş)
    assert client.get(f"/yonetici/siparisler/{order.id}").status_code == 200


# --- 2) ÇOK ÜRETİCİLİ SEPET + İPTAL ----------------------------------------------------

def test_multi_producer_cart_split_and_cancel_restores_stock(client):
    p1, l1 = producer_with_listing(client, "u1@example.com", "Çiftlik Bir", "Domates A", price="20")
    p2, l2 = producer_with_listing(client, "u2@example.com", "Çiftlik İki", "Domates B", price="10")

    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    client.post(f"/sepet/ekle/{l1.id}", data={"quantity": "5"})
    client.post(f"/sepet/ekle/{l2.id}", data={"quantity": "3"})
    client.post("/sepet/odeme", data={"shipping_address": ADDRESS, "note": ""})

    orders = Order.query.order_by(Order.id).all()
    assert len(orders) == 2                                  # her üreticiye ayrı sipariş
    assert {o.producer.farm_name for o in orders} == {"Çiftlik Bir", "Çiftlik İki"}
    assert CartItem.query.count() == 0                       # sepet boşaldı

    # Ödenmiş bir siparişi iptal et -> stok geri gelir, ödeme iade olur
    first = orders[0]
    set_status(client, first.id, OrderStatus.PAID)
    set_status(client, first.id, OrderStatus.CANCELLED)
    db.session.refresh(first)
    db.session.refresh(l1)
    db.session.refresh(p1)
    assert first.status == OrderStatus.CANCELLED
    assert first.payment.status == PaymentStatus.REFUNDED
    assert l1.stock_quantity == Decimal("50")
    assert p1.stock_quantity == Decimal("100")

    # İkinci üretici, birinci üreticinin siparişini göremez (sahiplik)
    logout(client)
    login(client, "u2@example.com")
    assert client.get(f"/uretici/siparisler/{first.id}").status_code == 404


# --- 3) DUMAN TESTİ (SMOKE TEST) -------------------------------------------------------

def test_smoke_every_page_opens_for_every_role(client):
    """Her rol için menüdeki sayfalar 500 vermeden açılmalı. Bir modül değişip başka
    bir sayfayı bozarsa (regresyon) bu test hemen yakalar."""
    product, listing = producer_with_listing(client, "uretici@example.com", "Yeşil Vadi", "Biber")

    public_pages = ["/", "/ilanlar", f"/ilanlar/{listing.id}", "/ilanlar?q=biber",
                    "/auth/login", "/auth/register"]
    for url in public_pages:
        assert client.get(url).status_code == 200, url

    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "2"})
    client.post("/sepet/odeme", data={"shipping_address": ADDRESS, "note": ""})
    order = Order.query.one()
    for url in ["/musteri/panel", "/sepet/", "/siparislerim", f"/siparislerim/{order.id}"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/sepet/odeme").status_code == 302     # sepet boş -> ilanlara yönlenir
    logout(client)

    login(client, "uretici@example.com")
    for url in ["/uretici/panel", "/uretici/profil", "/uretici/urunler", "/uretici/urunler/yeni",
                f"/uretici/urunler/{product.id}/duzenle", "/uretici/ilanlar", "/uretici/ilanlar/yeni",
                f"/uretici/ilanlar/{listing.id}/duzenle", "/uretici/siparisler",
                f"/uretici/siparisler/{order.id}", "/uretici/siparisler?durum=pending"]:
        assert client.get(url).status_code == 200, url
    logout(client)

    create_admin_user("Yönetici", "admin@example.com", "Yonetici123")
    login(client, "admin@example.com", "Yonetici123")
    for url in ["/yonetici/panel", "/yonetici/siparisler", "/yonetici/siparisler?durum=pending",
                f"/yonetici/siparisler/{order.id}", "/yonetici/kategoriler", "/yonetici/kategoriler/yeni"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/panel").headers["Location"].endswith("/yonetici/panel")


def test_role_boundaries_between_modules(client):
    """Bir rolün sayfası başka role kapalı olmalı (yetkilendirme modülü x diğer modüller)."""
    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    for url in ["/uretici/panel", "/uretici/ilanlar", "/yonetici/panel", "/yonetici/siparisler"]:
        assert client.get(url).status_code == 403, url
    logout(client)
    assert client.get("/sepet/").status_code == 302          # giriş yapmamış -> giriş sayfası


def test_version_shown_in_footer(client):
    """Sürüm numarası Semantic Versioning biçiminde ve sayfada görünüyor."""
    major, minor, patch = __version__.split(".")
    assert major.isdigit() and minor.isdigit() and patch.isdigit()
    assert f"v{__version__}" in client.get("/").get_data(as_text=True)


# --- 4) REGRESYON TESTLERİ (Hafta 8'de düzeltilen hatalar) -----------------------------

def test_regression_sqlite_foreign_keys_enforced(app):
    """HATA 1: SQLite'ta yabancı anahtar denetimi kapalıydı; yerelde geçen hatalı kayıt
    canlıda (PostgreSQL) patlıyordu. Artık iki ortam da aynı davranır."""
    assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_regression_delete_product_that_is_in_a_cart(client):
    """HATA 2: Bir müşterinin sepetinde ilanı bulunan ürün silinince 500 hatası (IntegrityError)
    çıkıyordu. Artık önce sepet kalemleri silinir, sonra ürün ve ilanları."""
    product, listing = producer_with_listing(client, "uretici@example.com", "Yeşil Vadi", "Kayısı")
    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "2"})
    assert CartItem.query.count() == 1
    logout(client)

    login(client, "uretici@example.com")
    response = client.post(f"/uretici/urunler/{product.id}/sil", follow_redirects=True)
    assert response.status_code == 200
    assert db.session.get(Product, product.id) is None
    assert CartItem.query.count() == 0
    logout(client)

    login(client, "musteri@example.com")
    assert client.get("/sepet/").status_code == 200          # sepet sayfası da bozulmadı


def test_regression_unit_cannot_change_when_product_has_listings(client):
    """HATA 3: İlanı olan ürünün birimi kg -> adet yapılabiliyordu; '2,5 kg' ilan '2,5 adet'e
    dönüşüyor, eski siparişler de yanlış birimle görünüyordu."""
    product, listing = producer_with_listing(client, "uretici@example.com", "Yeşil Vadi", "Bal")
    login(client, "uretici@example.com")
    page = client.post(f"/uretici/urunler/{product.id}/duzenle", data={
        "name": "Bal", "category_id": str(product.category_id), "unit": "adet",
        "stock_quantity": "100", "is_active": "y",
    }, follow_redirects=True)
    assert "birimi değiştirilemez" in page.get_data(as_text=True)
    db.session.refresh(product)
    assert product.unit == "kg"


def test_regression_admin_status_change_returns_to_order(client):
    """HATA 4: Yönetici sipariş durumunu değiştirince panele atılıyordu, siparişi kaybediyordu."""
    _, listing = producer_with_listing(client, "uretici@example.com", "Yeşil Vadi", "Fasulye")
    register(client, "musteri@example.com", "customer")
    login(client, "musteri@example.com")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "2"})
    client.post("/sepet/odeme", data={"shipping_address": ADDRESS, "note": ""})
    order = Order.query.one()
    logout(client)

    create_admin_user("Yönetici", "admin@example.com", "Yonetici123")
    login(client, "admin@example.com", "Yonetici123")
    response = client.post(f"/siparis/{order.id}/durum", data={"new_status": OrderStatus.CANCELLED})
    assert response.headers["Location"].endswith(f"/yonetici/siparisler/{order.id}")
    db.session.refresh(order)
    assert order.status == OrderStatus.CANCELLED


# --- 5) DEMO VERİSİ (canlı sunumda kullanılan hesaplar) --------------------------------

def test_demo_data_is_synthetic_idempotent_and_usable(app, client, monkeypatch):
    """flask seed-demo: KVKK uyumlu (yalnızca example.com), iki kez çalışınca çoğalmaz,
    eklenen demo hesaplarla uçtan uca alışveriş yapılabilir."""
    from app.models import User
    from scripts.demo_data import seed_demo

    monkeypatch.setenv("DEMO_PASSWORD", "DemoParola123")
    assert "eklendi" in seed_demo()
    assert "zaten var" in seed_demo()                         # ikinci çalıştırma bir şey eklemez

    emails = [u.email for u in User.query.all()]
    assert len(emails) == 4                                   # 2 üretici + 1 müşteri + 1 yönetici
    assert all(e.endswith("@example.com") for e in emails)    # gerçek kişisel veri yok

    listing = Listing.query.filter_by(title="Kuru Fasulye").one()
    login(client, "musteri@example.com", "DemoParola123")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "3"})
    client.post("/sepet/odeme", data={"shipping_address": ADDRESS, "note": ""})
    assert Order.query.one().total_amount == Decimal("285.00")
    logout(client)

    login(client, "yonetici@example.com", "DemoParola123")
    assert 'data-test="order-total">1<' in client.get("/yonetici/panel").get_data(as_text=True)


def test_demo_products_have_sample_images(app, client, monkeypatch):
    """Demo ürünlerinin örnek görselleri var, dosyalar projede duruyor ve vitrinde görünüyor.
    Görselsiz eklenmiş eski demo ürünlerine (canlı site) sonraki çalıştırmada görsel eklenir."""
    import os

    from scripts.demo_data import seed_demo

    monkeypatch.setenv("DEMO_PASSWORD", "DemoParola123")
    seed_demo()
    products = Product.query.all()
    assert products and all(p.image_path and p.image_path.startswith("demo/") for p in products)
    for product in products:
        assert os.path.isfile(os.path.join(app.static_folder, "img", product.image_path))

    html = client.get("/ilanlar").get_data(as_text=True)
    assert "/static/img/demo/domates.jpg" in html

    # Canlıdaki gibi: ürünler önceden görselsiz veya eski görselle (v0.8.1 .png) eklenmiş olsun;
    # üreticinin kendi yüklediği görsele ise dokunulmamalı
    for product in products:
        product.image_path = None
    products[0].image_path = "demo/domates.png"
    products[1].image_path = "products/uretici-yukledi.jpg"
    db.session.commit()
    assert "5 görsel" in seed_demo()
    db.session.refresh(products[1])
    assert products[1].image_path == "products/uretici-yukledi.jpg"
    assert all(p.image_path.endswith(".jpg") for p in Product.query.all())
