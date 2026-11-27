"""Hafta 11 testleri: Değerlendirme ve İtibar Modülü.

Bölümler:
  1) İtibar hesabı (saf fonksiyon): Bayes ortalaması, her müşteri tek oy
  2) İş kuralları: yalnızca teslim edilmiş siparişin sahibi, kalem başına tek yorum, süre, puan aralığı
  3) Kötüye kullanım: bağlantı/telefon/e-posta, spam, gerekçesiz düşük puan, günlük sınır
  4) Yönetici moderasyonu ve itibarın yeniden hesaplanması
  5) Diğer modüllerle entegrasyon: ilan sayfası, ilan kartı, üretici paneli, CLI

Çalıştırma: python -m pytest -v tests/test_reviews.py
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Order, OrderStatus, Review
from app.repositories.review_repository import ReviewRepository
from app.services import review_service
from app.services.auth_service import create_admin_user
from app.services.errors import ServiceError
from app.services.review_service import compute_reputation, content_problem
from tests.test_shop import checkout, customer_with_cart, set_status, setup_listing

PASSWORD = "Parola123"
PRODUCER = "ciftci@test.com"


def login(client, email, password=PASSWORD):
    client.post("/auth/logout")
    client.post("/auth/login", data={"email": email, "password": password})


def delivered_order(client, customer="musteri@test.com", listing=None):
    """Üretici ilanı -> müşteri sipariş -> öder -> üretici kargolar -> müşteri teslim alır."""
    listing = listing or setup_listing(client)
    customer_with_cart(client, listing, email=customer)
    checkout(client)
    order = Order.query.order_by(Order.id.desc()).first()
    set_status(client, order, OrderStatus.PAID)
    login(client, PRODUCER)
    set_status(client, order, OrderStatus.SHIPPED)
    login(client, customer)
    set_status(client, order, OrderStatus.DELIVERED)
    assert order.status == OrderStatus.DELIVERED
    return order


def review(client, order, rating="5", comment="Taze ve lezzetliydi, teşekkürler.", item=None):
    item = item or order.items[0]
    return client.post(f"/siparislerim/{order.id}/kalem/{item.id}/degerlendir",
                       data={"rating": rating, "comment": comment}, follow_redirects=True)


# --- 1) İtibar hesabı -----------------------------------------------------------------------

def test_reputation_empty():
    assert compute_reputation([]) == (0.0, 0)


def test_bayesian_average_pulls_few_votes_to_platform_mean():
    # Tek bir 5 yıldız "5,0" itibar yapmaz: (5×4 + 5) / (5 + 1) = 4,17
    assert compute_reputation([(1, 5)], prior_mean=4.0, prior_weight=5) == (4.17, 1)
    # Çok oy olunca puan gerçek ortalamaya yaklaşır: 20 müşteri × 4,8 -> (20 + 96) / 25 = 4,64
    votes = [(customer, 5 if customer % 5 else 4) for customer in range(1, 21)]  # ortalama 4,8
    assert compute_reputation(votes, prior_mean=4.0, prior_weight=5) == (4.64, 20)


def test_one_customer_one_vote():
    # Aynı müşteri 10 kez 1 yıldız verse de tek oy (ortalaması 1) sayılır
    many = [(7, 1)] * 10 + [(8, 5), (9, 5)]
    score, voters = compute_reputation(many, prior_mean=4.0, prior_weight=5)
    assert voters == 3
    assert score == round((5 * 4 + 1 + 5 + 5) / 8, 2)  # 3,88 — 10 oy gibi sayılsaydı 2'nin altına düşerdi


# --- 2) İş kuralları --------------------------------------------------------------------------

def test_full_flow_review_updates_reputation(client):
    order = delivered_order(client)
    page = review(client, order, "5").get_data(as_text=True)
    assert "Değerlendirmeniz için teşekkürler" in page
    saved = Review.query.one()
    assert saved.rating == 5 and saved.customer_id == order.customer_id
    assert saved.producer_id == order.items[0].producer_id
    producer = order.items[0].producer
    assert producer.review_count == 1 and producer.reputation_score == 5.0
    assert "Taze ve lezzetliydi" in page  # sipariş sayfasında yorum görünür, form yok


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.PAID])
def test_cannot_review_before_delivery(client, status):
    listing = setup_listing(client)
    customer_with_cart(client, listing)
    checkout(client)
    order = Order.query.one()
    if status == OrderStatus.PAID:
        set_status(client, order, OrderStatus.PAID)
    page = review(client, order).get_data(as_text=True)
    assert "teslim edildikten sonra" in page and Review.query.count() == 0


def test_cannot_review_cancelled_order(client):
    listing = setup_listing(client)
    customer_with_cart(client, listing)
    checkout(client)
    order = Order.query.one()
    set_status(client, order, OrderStatus.CANCELLED)
    assert "teslim edildikten sonra" in review(client, order).get_data(as_text=True)
    assert Review.query.count() == 0


def test_only_once_per_item(client):
    order = delivered_order(client)
    review(client, order, "5")
    page = review(client, order, "1", "İkinci kez yazıyorum, çok kötüydü aslında.").get_data(as_text=True)
    assert "zaten değerlendirdiniz" in page
    assert Review.query.one().rating == 5


def test_database_enforces_one_review_per_item_and_rating_range(client):
    order = delivered_order(client)
    item = order.items[0]
    db.session.add(Review(order_item=item, customer_id=order.customer_id, producer_id=item.producer_id, rating=6))
    with pytest.raises(IntegrityError):  # CHECK rating BETWEEN 1 AND 5
        db.session.commit()
    db.session.rollback()
    review(client, order, "4")
    db.session.add(Review(order_item_id=item.id, customer_id=order.customer_id, producer_id=item.producer_id, rating=3))
    with pytest.raises(IntegrityError):  # UNIQUE order_item_id
        db.session.commit()
    db.session.rollback()


def test_other_customer_gets_404(client):
    order = delivered_order(client)
    client.post("/auth/logout")
    customer_with_cart(client, order.items[0].listing, email="baska@test.com")
    assert client.post(f"/siparislerim/{order.id}/kalem/{order.items[0].id}/degerlendir",
                       data={"rating": "1", "comment": "Hiç almadım ama kötü diyorum işte."}).status_code == 404
    assert Review.query.count() == 0


def test_item_from_another_order_gets_404(client):
    order = delivered_order(client)
    assert client.post(f"/siparislerim/{order.id}/kalem/9999/degerlendir",
                       data={"rating": "5"}).status_code == 404


def test_producer_cannot_review(client):
    order = delivered_order(client)
    login(client, PRODUCER)
    assert client.post(f"/siparislerim/{order.id}/kalem/{order.items[0].id}/degerlendir",
                       data={"rating": "5"}).status_code == 403


def test_review_window_expired(client):
    order = delivered_order(client)
    order.updated_at = datetime.now(timezone.utc) - timedelta(days=review_service.REVIEW_WINDOW_DAYS + 1)
    db.session.commit()
    assert "süresi doldu" in review(client, order).get_data(as_text=True)


@pytest.mark.parametrize("rating", ["0", "6", "abc", ""])
def test_invalid_rating_rejected(client, rating):
    order = delivered_order(client)
    review(client, order, rating)
    assert Review.query.count() == 0


def test_service_rejects_invalid_rating_even_without_form(client):
    order = delivered_order(client)
    with pytest.raises(ServiceError, match="1 ile 5"):
        review_service.create_review(order.customer, order.items[0], 9)
    with pytest.raises(ServiceError, match="1 ile 5"):
        review_service.create_review(order.customer, order.items[0], True)  # bool sayı sayılmaz


# --- 3) Kötüye kullanım önleme ----------------------------------------------------------------

@pytest.mark.parametrize("comment, rating, problem", [
    ("", 1, "nedenini"),                                            # gerekçesiz düşük puan
    ("kötü", 2, "nedenini"),
    ("Daha ucuzu için www.baskasite.com adresine bakın", 5, "bağlantı"),
    ("İndirim kodu: https://ornek.xyz/kod", 4, "bağlantı"),
    ("Beni arayın 0532 123 45 67 toptan veririm", 5, "telefon"),
    ("Bilgi için yazın: satici@ornek.com", 5, "e-posta"),
    ("Harikaaaaaaaaa!!!!!!!!", 5, "tekrarlamayın"),
    ("BU ÜRETİCİDEN SAKIN ALMAYIN ÇOK KÖTÜ", 1, "büyük harf"),
    ("x" * 501, 5, "500"),
])
def test_content_rules(comment, rating, problem):
    assert problem in (content_problem(comment, rating) or "")


@pytest.mark.parametrize("comment, rating", [
    ("", 5), ("Domatesler çok tazeydi.", 4), ("Ürün geç geldi, biraz ezilmişti ama tadı güzeldi.", 2),
    ("Çoook güzel", 5),  # birkaç harf uzatmak serbest; 6+ tekrar değil
])
def test_normal_comments_allowed(comment, rating):
    assert content_problem(comment, rating) is None


def test_link_in_comment_rejected_via_form(client):
    order = delivered_order(client)
    page = review(client, order, "5", "Daha iyisi için www.rakip.com").get_data(as_text=True)
    assert "bağlantı" in page and Review.query.count() == 0


def test_daily_limit(client, monkeypatch):
    order = delivered_order(client)
    monkeypatch.setattr(ReviewRepository, "count_by_customer_since",
                        staticmethod(lambda customer_id, since: review_service.DAILY_REVIEW_LIMIT))
    assert "en fazla" in review(client, order).get_data(as_text=True)
    assert Review.query.count() == 0


# --- 4) Yönetici moderasyonu --------------------------------------------------------------------

def test_admin_hides_review_and_reputation_recomputed(client):
    order = delivered_order(client)
    review(client, order, "5")
    producer = order.items[0].producer
    assert producer.review_count == 1

    create_admin_user("Yönetici", "yonetici@test.com", PASSWORD)
    login(client, "yonetici@test.com")
    saved = Review.query.one()
    page = client.post(f"/yonetici/degerlendirmeler/{saved.id}/gorunurluk", follow_redirects=True).get_data(as_text=True)
    assert "gizlendi" in page
    db.session.refresh(producer)
    assert saved.is_visible is False and producer.review_count == 0 and producer.reputation_score == 0.0

    # Gizli yorum ilan sayfasında görünmez
    assert "Taze ve lezzetliydi" not in client.get(f"/ilanlar/{order.items[0].listing_id}").get_data(as_text=True)

    client.post(f"/yonetici/degerlendirmeler/{saved.id}/gorunurluk")  # yeniden yayına al
    db.session.refresh(producer)
    assert saved.is_visible and producer.review_count == 1


def test_non_admin_cannot_moderate(client):
    order = delivered_order(client)
    review(client, order, "5")
    saved = Review.query.one()
    assert client.post(f"/yonetici/degerlendirmeler/{saved.id}/gorunurluk").status_code == 403
    assert client.get("/yonetici/degerlendirmeler").status_code == 403
    assert saved.is_visible


def test_one_customer_many_orders_counts_once(client):
    """Aynı müşteri aynı üreticiden iki kez alıp iki kez 1 yıldız verse de itibara tek oy girer."""
    listing = setup_listing(client, stock="40")
    first = delivered_order(client, listing=listing)
    review(client, first, "1", "Ürünler ezik geldi, paketleme yetersizdi.")
    second = delivered_order(client, listing=listing)
    review(client, second, "1", "Yine ezik geldi, paketleme hiç düzelmemiş.")
    producer = listing.producer
    assert producer.review_count == 2                     # iki yorum görünür
    assert compute_reputation([(r.customer_id, r.rating) for r in producer.reviews])[1] == 1  # tek oy


# --- 5) Entegrasyon ----------------------------------------------------------------------------

def test_review_shown_on_listing_page_card_and_producer_page(client):
    order = delivered_order(client)
    review(client, order, "4", "Güzeldi, bir sonraki siparişte de alırım.")
    listing_id = order.items[0].listing_id

    detail = client.get(f"/ilanlar/{listing_id}").get_data(as_text=True)
    assert "Güzeldi, bir sonraki" in detail and "Satın aldı" in detail
    assert "Bu ürün: <strong>4.0</strong>/5 (1)" in detail
    section = detail.split("bi-chat-square-text", 1)[1]  # yalnızca "Değerlendirmeler" bölümü
    assert "Test ·" in section and "Test Kullanıcı" not in section  # yalnızca adın ilk kelimesi (KVKK)

    assert "bi-star-fill text-warning" in client.get("/ilanlar").get_data(as_text=True)  # kartta itibar

    login(client, PRODUCER)
    page = client.get("/uretici/degerlendirmeler").get_data(as_text=True)
    assert "Güzeldi, bir sonraki" in page and "Sipariş #" in page
    assert "Değerlendirmeleri gör" in client.get("/uretici/panel").get_data(as_text=True)


def test_review_form_only_for_delivered_order_owner(client):
    order = delivered_order(client)
    page = client.get(f"/siparislerim/{order.id}").get_data(as_text=True)
    assert "Ürünleri değerlendirin" in page and "degerlendir" in page
    login(client, PRODUCER)
    assert "Ürünleri değerlendirin" not in client.get(f"/uretici/siparisler/{order.id}").get_data(as_text=True)


def test_cli_recompute_reputation(app, client):
    order = delivered_order(client)
    review(client, order, "5")
    producer = order.items[0].producer
    producer.reputation_score, producer.review_count = 0.0, 0  # önbellek bozulmuş olsun
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["recompute-reputation"])
    assert "1 üreticinin" in result.output
    db.session.refresh(producer)
    assert producer.review_count == 1 and producer.reputation_score == 5.0
