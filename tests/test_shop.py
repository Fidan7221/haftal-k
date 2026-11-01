"""Hafta 7 testleri: ilan, sepet, sipariş ve durum yönetimi.

Çalıştırma: pytest -v tests/test_shop.py
"""
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (
    Category, Listing, ListingStatus, Order, OrderStatus, Payment, PaymentStatus, Product,
)
from app.repositories.user_repository import UserRepository
from tests.conftest import register_and_login


# --- Yardımcılar -------------------------------------------------------------------

def make_product(email, name="Domates", stock="100", unit="kg", active=True):
    """Doğrudan veri tabanına ürün ekler (ürün CRUD'u Hafta 6'da test edildi)."""
    profile = UserRepository.get_by_email(email).producer_profile
    product = Product(producer=profile, category=Category.query.filter_by(slug="domates").first(),
                      name=name, unit=unit, stock_quantity=Decimal(stock), is_active=active)
    db.session.add(product)
    db.session.commit()
    return product


def listing_data(product_id, **overrides):
    data = {"product_id": str(product_id), "title": "Taze domates", "price": "25",
            "stock_quantity": "40", "min_order_quantity": "2", "end_date": ""}
    data.update(overrides)
    return data


def open_listing(client, product_id, **overrides):
    return client.post("/uretici/ilanlar/yeni", data=listing_data(product_id, **overrides),
                       follow_redirects=True)


def logout(client):
    client.post("/auth/logout")


def setup_listing(client, stock="40", price="25", product_stock="100", min_order="2", unit="kg",
                  producer="ciftci@test.com", farm="Test Çiftliği"):
    """Bir üretici + ürün + ilan hazırlar ve oturumu kapatır."""
    register_and_login(client, producer, farm_name=farm)
    product = make_product(producer, stock=product_stock, unit=unit)
    open_listing(client, product.id, stock_quantity=stock, price=price, min_order_quantity=min_order)
    logout(client)
    return Listing.query.filter_by(product_id=product.id).one()


def customer_with_cart(client, listing, quantity="5", email="musteri@test.com"):
    register_and_login(client, email, role="customer")
    return client.post(f"/sepet/ekle/{listing.id}", data={"quantity": quantity}, follow_redirects=True)


def checkout(client, address="Yenişehir Mah. Örnek Sok. No:1 Merkez / Bingöl"):
    return client.post("/sepet/odeme", data={"shipping_address": address, "note": ""},
                       follow_redirects=True)


def set_status(client, order, new_status):
    return client.post(f"/siparis/{order.id}/durum", data={"new_status": new_status},
                       follow_redirects=True)


# --- İLAN ---------------------------------------------------------------------------

def test_producer_creates_listing(client):
    listing = setup_listing(client)
    assert listing.price == Decimal("25.00")
    assert listing.stock_quantity == Decimal("40.00")
    assert listing.status == ListingStatus.ACTIVE


def test_listing_visible_in_public_list(client):
    setup_listing(client)
    html = client.get("/ilanlar").get_data(as_text=True)
    assert "Taze domates" in html
    assert "Test Çiftliği" in html


def test_listing_cannot_exceed_product_stock(client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", stock="30")
    response = open_listing(client, product.id, stock_quantity="31")
    assert "en fazla 30 kg" in response.get_data(as_text=True)
    assert Listing.query.count() == 0


def test_total_open_listings_cannot_exceed_stock(client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", stock="50")
    open_listing(client, product.id, stock_quantity="30")
    response = open_listing(client, product.id, stock_quantity="30")  # 30 + 30 > 50
    assert "en fazla 20 kg" in response.get_data(as_text=True)
    assert Listing.query.count() == 1


def test_listing_validation_rules(client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com")
    html = open_listing(client, product.id, price="0").get_data(as_text=True)
    assert "Fiyat sıfırdan büyük olmalı" in html
    html = open_listing(client, product.id, min_order_quantity="50").get_data(as_text=True)
    assert "En az sipariş miktarı, satışa ayrılan miktardan büyük olamaz" in html
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    html = open_listing(client, product.id, end_date=yesterday).get_data(as_text=True)
    assert "Bitiş tarihi geçmişte olamaz" in html
    assert Listing.query.count() == 0


def test_piece_unit_requires_whole_number(client):
    register_and_login(client, "ciftci@test.com")
    product = make_product("ciftci@test.com", unit="kasa")
    html = open_listing(client, product.id, stock_quantity="2.5", min_order_quantity="1").get_data(as_text=True)
    assert "tam sayı" in html


def test_cannot_list_archived_product(client):
    register_and_login(client, "ciftci@test.com")
    active = make_product("ciftci@test.com", name="Aktif")
    archived = make_product("ciftci@test.com", name="Arşiv", active=False)
    open_listing(client, archived.id)
    assert Listing.query.count() == 0
    open_listing(client, active.id)
    assert Listing.query.count() == 1


def test_producer_cannot_edit_others_listing(client):
    listing = setup_listing(client)
    register_and_login(client, "baska@test.com", farm_name="Başka Çiftlik")
    assert client.get(f"/uretici/ilanlar/{listing.id}/duzenle").status_code == 404
    assert client.post(f"/uretici/ilanlar/{listing.id}/kapat").status_code == 404
    assert client.post(f"/uretici/ilanlar/{listing.id}/duzenle",
                       data=listing_data(listing.product_id, price="1")).status_code == 404
    assert db.session.get(Listing, listing.id).price == Decimal("25.00")


def test_customer_cannot_open_listing(client):
    register_and_login(client, "musteri@test.com", role="customer")
    assert client.get("/uretici/ilanlar/yeni").status_code == 403


def test_close_and_reopen_listing(client):
    listing = setup_listing(client)
    register_and_login(client, "ciftci@test.com")
    client.post(f"/uretici/ilanlar/{listing.id}/kapat", follow_redirects=True)  # flash mesajı tüketilsin
    assert db.session.get(Listing, listing.id).status == ListingStatus.CLOSED
    assert "Taze domates" not in client.get("/ilanlar").get_data(as_text=True)
    client.post(f"/uretici/ilanlar/{listing.id}/ac")
    assert db.session.get(Listing, listing.id).status == ListingStatus.ACTIVE


def test_product_stock_cannot_drop_below_listed(client):
    listing = setup_listing(client)  # 40 kg ilanda
    register_and_login(client, "ciftci@test.com")
    html = client.post(f"/uretici/urunler/{listing.product_id}/stok", data={"quantity": "10"},
                       follow_redirects=True).get_data(as_text=True)
    assert "stok bundan az olamaz" in html
    assert db.session.get(Product, listing.product_id).stock_quantity == Decimal("100.00")


# --- SEPET --------------------------------------------------------------------------

def test_add_to_cart_and_merge_same_listing(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing, "3")
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "2"})
    user = UserRepository.get_by_email("musteri@test.com")
    assert len(user.cart.items) == 1                       # yeni satır açılmadı
    assert user.cart.items[0].quantity == Decimal("5.00")  # miktar toplandı


def test_cart_respects_min_order_and_stock(client):
    listing = setup_listing(client, stock="10", min_order="2")
    html = customer_with_cart(client, listing, "1").get_data(as_text=True)
    assert "En az 2 kg" in html
    html = client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "11"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Stokta yalnızca 10 kg" in html
    assert UserRepository.get_by_email("musteri@test.com").cart is None or \
        not UserRepository.get_by_email("musteri@test.com").cart.items


def test_cart_does_not_reduce_stock(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing, "5")
    assert db.session.get(Listing, listing.id).stock_quantity == Decimal("40.00")


def test_producer_cannot_use_cart(client):
    listing = setup_listing(client)
    register_and_login(client, "ciftci@test.com")
    assert client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "3"}).status_code == 403


def test_cannot_touch_others_cart_item(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing, "3", email="ayse@test.com")
    item_id = UserRepository.get_by_email("ayse@test.com").cart.items[0].id
    logout(client)
    register_and_login(client, "mehmet@test.com", role="customer")
    assert client.post(f"/sepet/kalem/{item_id}/guncelle", data={"quantity": "9"}).status_code == 404
    assert client.post(f"/sepet/kalem/{item_id}/sil").status_code == 404


def test_update_to_zero_removes_item(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing, "3")
    item_id = UserRepository.get_by_email("musteri@test.com").cart.items[0].id
    client.post(f"/sepet/kalem/{item_id}/guncelle", data={"quantity": "0"})
    assert UserRepository.get_by_email("musteri@test.com").cart.items == []


# --- SEPETTEN SİPARİŞE ------------------------------------------------------------

def test_checkout_creates_order_and_reduces_stock(client):
    listing = setup_listing(client, stock="40", price="25")
    customer_with_cart(client, listing, "4")
    html = checkout(client).get_data(as_text=True)

    order = Order.query.one()
    assert "Siparişiniz oluşturuldu" in html
    assert order.status == OrderStatus.PENDING
    assert order.total_amount == Decimal("100.00")
    assert order.items[0].unit_price == Decimal("25.00")
    assert db.session.get(Listing, listing.id).stock_quantity == Decimal("36.00")
    assert db.session.get(Product, listing.product_id).stock_quantity == Decimal("96.00")
    assert UserRepository.get_by_email("musteri@test.com").cart.items == []  # sepet boşaldı


def test_price_is_frozen_after_order(client):
    listing = setup_listing(client, price="25")
    customer_with_cart(client, listing, "4")
    checkout(client)
    listing = db.session.get(Listing, listing.id)
    listing.price = Decimal("99")  # üretici fiyatı sonradan değiştirdi
    db.session.commit()
    assert Order.query.one().total_amount == Decimal("100.00")


def test_checkout_splits_order_per_producer(client):
    first = setup_listing(client, producer="ali@test.com", farm="Ali Çiftliği")
    second = setup_listing(client, producer="veli@test.com", farm="Veli Çiftliği")
    customer_with_cart(client, first, "2")
    client.post(f"/sepet/ekle/{second.id}", data={"quantity": "3"})
    html = checkout(client).get_data(as_text=True)
    assert "2 ayrı sipariş" in html
    orders = Order.query.all()
    assert len(orders) == 2
    assert {o.producer.farm_name for o in orders} == {"Ali Çiftliği", "Veli Çiftliği"}


def test_checkout_rolls_back_when_stock_gone(client):
    listing = setup_listing(client, stock="10")
    customer_with_cart(client, listing, "8")
    # Başka bir müşteri bu arada stoğu aldı gibi yapalım
    db.session.get(Listing, listing.id).stock_quantity = Decimal("5")
    db.session.commit()
    html = checkout(client).get_data(as_text=True)
    assert "Stokta yalnızca 5 kg" in html
    assert Order.query.count() == 0                                    # sipariş oluşmadı
    assert db.session.get(Listing, listing.id).stock_quantity == Decimal("5.00")  # stok değişmedi


def test_last_stock_marks_listing_sold_out(client):
    listing = setup_listing(client, stock="10")
    customer_with_cart(client, listing, "10")
    checkout(client)
    listing = db.session.get(Listing, listing.id)
    assert listing.stock_quantity == 0
    assert listing.status == ListingStatus.SOLD_OUT


def test_checkout_requires_address(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing, "3")
    html = checkout(client, address="kısa").get_data(as_text=True)
    assert "Adres 10-255 karakter olmalı" in html
    assert Order.query.count() == 0


# --- SİPARİŞ DURUMLARI -----------------------------------------------------------

def place_order(client, quantity="4"):
    listing = setup_listing(client)
    customer_with_cart(client, listing, quantity)
    checkout(client)
    return listing, Order.query.one()


def test_full_lifecycle(client):
    listing, order = place_order(client)
    set_status(client, order, OrderStatus.PAID)                 # müşteri öder
    assert order.status == OrderStatus.PAID
    assert order.payment.status == PaymentStatus.SUCCESS
    logout(client)

    register_and_login(client, "ciftci@test.com")
    set_status(client, order, OrderStatus.SHIPPED)              # üretici kargolar
    assert order.status == OrderStatus.SHIPPED
    logout(client)

    register_and_login(client, "musteri@test.com", role="customer")
    set_status(client, order, OrderStatus.DELIVERED)            # müşteri teslim alır
    assert order.status == OrderStatus.DELIVERED


def test_invalid_transition_rejected(client):
    _, order = place_order(client)
    html = set_status(client, order, OrderStatus.DELIVERED).get_data(as_text=True)  # pending -> delivered
    assert "durumuna geçemez" in html
    assert order.status == OrderStatus.PENDING


def test_customer_cannot_ship(client):
    _, order = place_order(client)
    set_status(client, order, OrderStatus.PAID)
    html = set_status(client, order, OrderStatus.SHIPPED).get_data(as_text=True)
    assert "yetkiniz yok" in html
    assert order.status == OrderStatus.PAID


def test_delivered_is_final(client):
    _, order = place_order(client)
    order.status = OrderStatus.DELIVERED
    db.session.commit()
    set_status(client, order, OrderStatus.CANCELLED)
    assert order.status == OrderStatus.DELIVERED


def test_cancel_restores_stock_and_refunds(client):
    listing, order = place_order(client, quantity="40")  # ilanın tamamı -> tükendi
    assert db.session.get(Listing, listing.id).status == ListingStatus.SOLD_OUT
    set_status(client, order, OrderStatus.PAID)
    set_status(client, order, OrderStatus.CANCELLED)

    listing = db.session.get(Listing, listing.id)
    assert order.status == OrderStatus.CANCELLED
    assert order.payment.status == PaymentStatus.REFUNDED
    assert listing.stock_quantity == Decimal("40.00")
    assert listing.status == ListingStatus.ACTIVE  # tekrar satışta
    assert db.session.get(Product, listing.product_id).stock_quantity == Decimal("100.00")


def test_other_customer_cannot_see_order(client):
    _, order = place_order(client)
    logout(client)
    register_and_login(client, "baska@test.com", role="customer")
    assert client.get(f"/siparislerim/{order.id}").status_code == 404
    assert set_status(client, order, OrderStatus.CANCELLED).status_code == 404
    assert order.status == OrderStatus.PENDING


def test_other_producer_cannot_see_order(client):
    _, order = place_order(client)
    logout(client)
    register_and_login(client, "baska@test.com", farm_name="Başka Çiftlik")
    assert client.get(f"/uretici/siparisler/{order.id}").status_code == 404
    assert "#%d" % order.id not in client.get("/uretici/siparisler").get_data(as_text=True)


def test_producer_sees_incoming_order(client):
    _, order = place_order(client)
    logout(client)
    register_and_login(client, "ciftci@test.com")
    assert f"#{order.id}" in client.get("/uretici/siparisler").get_data(as_text=True)
    assert client.get(f"/uretici/siparisler/{order.id}").status_code == 200


def test_listing_with_orders_is_closed_not_deleted(client):
    listing, _ = place_order(client)
    logout(client)
    register_and_login(client, "ciftci@test.com")
    client.post(f"/uretici/ilanlar/{listing.id}/sil")
    listing = db.session.get(Listing, listing.id)
    assert listing is not None
    assert listing.status == ListingStatus.CLOSED
