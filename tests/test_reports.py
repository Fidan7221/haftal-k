"""Hafta 12 testleri: Satış raporu ve bildirimler.

Bölümler:
  1) Rapor hesapları: ciroya giren durumlar, ortalama, iptal oranı, birime göre miktar,
     en çok satanlar, günlük seri (Türkiye günü, boş gün = 0), önceki dönem, üretici ayrımı
  2) Rapor sayfaları, yetki ve CSV dışa aktarma
  3) Bildirim tetikleyicileri: kime, ne zaman; tekrar yok; geri alınan işlemde bildirim yok
  4) Bildirim sayfası: zil sayacı, okundu, başkasının bildirimi, güvenli yönlendirme

Çalıştırma: python -m pytest -v tests/test_reports.py
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.integrations.http import ApiTimeoutError
from app.integrations.payment_api import _mock_gateway
from app.models import Listing, Notification, NotificationKind, Order, OrderStatus
from app.repositories.order_repository import StatsRepository
from app.services import notification_service, report_service
from app.services.auth_service import create_admin_user
from app.services.report_service import TR, bar_chart, sales_report
from tests.conftest import register_and_login
from tests.test_shop import checkout, customer_with_cart, make_product, open_listing, set_status, setup_listing

PASSWORD = "Parola123"
PRODUCER = "ciftci@test.com"
CUSTOMER = "musteri@test.com"


def login(client, email):
    client.post("/auth/logout")
    client.post("/auth/login", data={"email": email, "password": PASSWORD})


def buy(client, listing, quantity="5", customer=CUSTOMER):
    """Müşteri sepete ekler ve sipariş oluşturur (ödeme BEKLİYOR). Yeni siparişi döndürür."""
    if _exists(customer):
        login(client, customer)
        client.post(f"/sepet/ekle/{listing.id}", data={"quantity": quantity})
    else:
        customer_with_cart(client, listing, quantity=quantity, email=customer)
    checkout(client)
    return Order.query.order_by(Order.id.desc()).first()


def _exists(email):
    from app.repositories.user_repository import UserRepository
    return UserRepository.get_by_email(email) is not None


def paid(client, listing, quantity="5", customer=CUSTOMER):
    order = buy(client, listing, quantity, customer)
    set_status(client, order, OrderStatus.PAID)
    return order


def producer_id():
    from app.repositories.user_repository import UserRepository
    return UserRepository.get_by_email(PRODUCER).producer_profile.id


def notes(email, kind=None):
    from app.repositories.user_repository import UserRepository
    query = Notification.query.filter_by(user_id=UserRepository.get_by_email(email).id)
    return query.filter_by(kind=kind).all() if kind else query.all()


# --- 1) Rapor hesapları --------------------------------------------------------------------------

def test_revenue_counts_only_paid_shipped_delivered(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    paid(client, listing, "5")                             # 50 TL ciro
    shipped = paid(client, listing, "2")                    # 20 TL ciro
    login(client, PRODUCER); set_status(client, shipped, OrderStatus.SHIPPED); login(client, CUSTOMER)
    buy(client, listing, "3")                               # bekliyor: 30 TL, ciroda YOK
    cancelled = paid(client, listing, "4")                  # iptal: ciroda YOK
    set_status(client, cancelled, OrderStatus.CANCELLED)

    report = sales_report(producer_id())
    c = report.current
    assert c.revenue == Decimal("70.00") and c.orders == 2
    assert c.avg_order == Decimal("35.00")
    assert c.pending == 1 and c.pending_amount == Decimal("30.00")
    assert c.cancelled == 1 and c.cancel_rate == pytest.approx(100 / 3)
    # Yönetici panelindeki (Hafta 8) ciro ile AYNI kural -> aynı sonuç
    assert sales_report(None).current.revenue == StatsRepository.get_summary_stats()["revenue"]


def test_quantity_by_unit_is_not_mixed_and_top_products_by_revenue(client):
    setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")  # Domates, kg
    login(client, PRODUCER)
    honey = make_product(PRODUCER, name="Çiçek Balı", unit="adet", stock="50")
    open_listing(client, honey.id, title="Çiçek Balı", price="300", stock_quantity="20", min_order_quantity="1")
    honey_listing = Listing.query.filter_by(product_id=honey.id).one()
    tomato = Listing.query.filter(Listing.product_id != honey.id).one()
    client.post("/auth/logout")
    paid(client, tomato, "8")        # 8 kg  -> 80 TL
    paid(client, honey_listing, "2")  # 2 adet -> 600 TL

    report = sales_report(producer_id())
    assert report.by_unit == [("adet", Decimal("2.00")), ("kg", Decimal("8.00"))]  # 10 "birim" diye toplanmaz
    assert [p["name"] for p in report.top_products] == ["Çiçek Balı", "Domates"]   # ciroya göre sıralı
    assert report.current.revenue == Decimal("680.00")


def test_daily_series_is_zero_filled_and_matches_total(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    paid(client, listing, "5")
    report = sales_report(producer_id(), days=7)
    assert len(report.daily) == 7                             # satışsız günler de var (0)
    assert sum(v for _, v in report.daily) == report.current.revenue
    assert sum(1 for _, v in report.daily if v == 0) == 6
    assert report.daily[-1][0] == datetime.now(timezone.utc).astimezone(TR).date()  # son gün bugün (TR)


def test_days_are_grouped_by_turkey_time(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    order = paid(client, listing, "5")
    # UTC 22:30 = Türkiye 01:30 (ERTESİ gün)
    order.created_at = datetime(2026, 11, 20, 22, 30, tzinfo=timezone.utc)
    db.session.commit()
    report = sales_report(producer_id(), days=7, now=datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc))
    assert dict(report.daily)[datetime(2026, 11, 21).date()] == Decimal("50.00")
    assert dict(report.daily)[datetime(2026, 11, 20).date()] == 0


def test_previous_period_change(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    old = paid(client, listing, "4")    # 40 TL, 10 gün önce
    paid(client, listing, "6")          # 60 TL, bugün
    old.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.session.commit()
    report = sales_report(producer_id(), days=7)
    assert report.current.revenue == Decimal("60.00") and report.previous.revenue == Decimal("40.00")
    assert report.revenue_change == pytest.approx(50.0)
    assert "%50 arttı" in report_service.summary_text(report)


def test_no_previous_sales_gives_no_percentage(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    paid(client, listing, "5")
    report = sales_report(producer_id())
    assert report.revenue_change is None  # 0'dan büyüme: "sonsuz %" gibi yanıltıcı sayı yok


def test_producer_sees_only_own_sales(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    other = setup_listing(client, stock="100", price="99", product_stock="200", min_order="1",
                          producer="baska@test.com", farm="Başka Çiftlik")
    paid(client, listing, "5")
    paid(client, other, "1")
    assert sales_report(producer_id()).current.revenue == Decimal("50.00")
    assert sales_report(None).current.revenue == Decimal("149.00")
    assert [farm for farm, _ in sales_report(None).by_producer] == ["Başka Çiftlik", "Test Çiftliği"]


def test_empty_report(app):
    report = sales_report(producer_id=12345, days=30)
    assert not report.has_data and report.current.avg_order is None and report.current.cancel_rate is None
    assert "sipariş yok" in report_service.summary_text(report)


def test_bar_chart_axis_starts_at_zero():
    day = datetime(2026, 11, 1).date()
    chart = bar_chart([(day, Decimal("0")), (day, Decimal("50")), (day, Decimal("100"))])
    bars = chart["bars"]
    assert bars[0]["h"] == 0                                   # satışsız gün: yüksekliği 0
    assert bars[2]["h"] == pytest.approx(2 * bars[1]["h"])      # 100 TL çubuğu 50 TL'nin tam iki katı
    assert all(b["y"] + b["h"] == pytest.approx(chart["base_y"]) for b in bars)  # hepsi 0 çizgisinden başlar
    assert chart["grid"][0]["label"] == "0,00"


# --- 2) Sayfalar, yetki, CSV --------------------------------------------------------------------------

def test_report_pages_and_access(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    paid(client, listing, "5")
    assert client.get("/uretici/rapor").status_code == 403      # müşteri
    login(client, PRODUCER)
    page = client.get("/uretici/rapor?gun=7").get_data(as_text=True)
    assert "Satış Raporu" in page and "50,00 TL" in page and "<svg" in page and "Son 7 gün" in page
    assert client.get("/uretici/rapor?gun=abc").status_code == 200  # geçersiz dönem -> 30 gün
    assert client.get("/yonetici/rapor").status_code == 403
    create_admin_user("Yönetici", "yonetici@test.com", PASSWORD)
    login(client, "yonetici@test.com")
    page = client.get("/yonetici/rapor").get_data(as_text=True)
    assert "Platform Satış Raporu" in page and "Üreticiye göre ciro" in page and "Test Çiftliği" in page


def test_csv_export(client):
    listing = setup_listing(client, stock="100", price="10.5", product_stock="200", min_order="1")
    listing.title = "=HYPERLINK(\"http://kotu.example\")"  # kullanıcıdan gelen metin formül gibi başlarsa
    listing.product.name = "=HYPERLINK(\"http://kotu.example\")"
    db.session.commit()
    paid(client, listing, "2")
    buy(client, listing, "1")  # bekleyen: CSV'de var ama "Ciroya dahil: Hayır"
    login(client, PRODUCER)
    response = client.get("/uretici/rapor.csv?gun=7")
    assert response.mimetype == "text/csv" and "attachment" in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    assert text.startswith("﻿")                     # Excel için BOM
    lines = text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("Sipariş no;Tarih;Durum;Ciroya dahil;Ürün")
    assert len(lines) == 3
    assert ";Evet;" in lines[1] and ";21,00" in lines[1]   # ondalık virgül
    assert ";Hayır;" in lines[2]
    assert "'=HYPERLINK" in text                         # formül enjeksiyonu etkisiz
    assert ";=HYPERLINK" not in text


# --- 3) Bildirim tetikleyicileri ------------------------------------------------------------------------

def test_order_lifecycle_notifications(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    order = buy(client, listing, "5")
    assert notes(PRODUCER, NotificationKind.ORDER_PAID) == []      # bekleyen siparişe bildirim yok
    set_status(client, order, OrderStatus.PAID)
    [n] = notes(PRODUCER, NotificationKind.ORDER_PAID)
    assert f"#{order.id} ödendi" in n.message and n.link == f"/uretici/siparisler/{order.id}"

    login(client, PRODUCER); set_status(client, order, OrderStatus.SHIPPED)
    assert len(notes(CUSTOMER, NotificationKind.ORDER_SHIPPED)) == 1
    login(client, CUSTOMER); set_status(client, order, OrderStatus.DELIVERED)
    [delivered] = notes(CUSTOMER, NotificationKind.ORDER_DELIVERED)
    assert "değerlendirebilirsiniz" in delivered.message
    assert len(notes(PRODUCER, NotificationKind.ORDER_DELIVERED)) == 1


def test_cancel_notifies_the_other_party(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    by_customer = paid(client, listing, "5")
    set_status(client, by_customer, OrderStatus.CANCELLED)          # müşteri iptal etti
    assert len(notes(PRODUCER, NotificationKind.ORDER_CANCELLED)) == 1
    assert notes(CUSTOMER, NotificationKind.ORDER_CANCELLED) == []  # kendine bildirim yok

    by_producer = paid(client, listing, "5")
    login(client, PRODUCER); set_status(client, by_producer, OrderStatus.CANCELLED)
    [n] = notes(CUSTOMER, NotificationKind.ORDER_CANCELLED)
    assert "iade edildi" in n.message
    assert len(notes(PRODUCER, NotificationKind.ORDER_CANCELLED)) == 1  # yalnızca ilki


def test_stock_alert_only_when_threshold_is_crossed(client):
    listing = setup_listing(client, stock="10", price="10", product_stock="200", min_order="1")
    buy(client, listing, "3")   # 10 -> 7: eşiğin üstünde, bildirim yok
    assert notes(PRODUCER, NotificationKind.STOCK_LOW) == []
    buy(client, listing, "3")   # 7 -> 4: eşik (5) aşıldı
    [low] = notes(PRODUCER, NotificationKind.STOCK_LOW)
    assert "4 kg kaldı" in low.message
    buy(client, listing, "1")   # 4 -> 3: yine az ama TEKRAR bildirim yok
    assert len(notes(PRODUCER, NotificationKind.STOCK_LOW)) == 1
    buy(client, listing, "3")   # 3 -> 0: bitti
    assert len(notes(PRODUCER, NotificationKind.STOCK_OUT)) == 1


def test_review_notifies_producer(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    order = paid(client, listing, "5")
    login(client, PRODUCER); set_status(client, order, OrderStatus.SHIPPED)
    login(client, CUSTOMER); set_status(client, order, OrderStatus.DELIVERED)
    client.post(f"/siparislerim/{order.id}/kalem/{order.items[0].id}/degerlendir", data={"rating": "5"})
    [n] = notes(PRODUCER, NotificationKind.REVIEW)
    assert "5 yıldızlı" in n.message and n.link == "/uretici/degerlendirmeler"


def test_failed_refund_creates_no_notification(client, monkeypatch):
    """Bildirim olayla aynı işlemde: iptal geri alınırsa 'iptal edildi' bildirimi de oluşmaz."""
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    order = paid(client, listing, "5")

    def broken_refund(*args, **kwargs):
        raise ApiTimeoutError("iade zaman aşımı")
    monkeypatch.setattr(_mock_gateway, "refund", broken_refund)
    set_status(client, order, OrderStatus.CANCELLED)
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert notes(PRODUCER, NotificationKind.ORDER_CANCELLED) == []


# --- 4) Bildirim sayfası -------------------------------------------------------------------------------

def test_bell_count_open_and_mark_all(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    first = paid(client, listing, "5")
    paid(client, listing, "5")
    login(client, PRODUCER)
    assert 'text-bg-warning">2</span>' in client.get("/").get_data(as_text=True)  # zil: 2 okunmamış
    page = client.get("/bildirimler").get_data(as_text=True)
    assert f"Sipariş #{first.id} ödendi" in page

    n = Notification.query.filter_by(kind=NotificationKind.ORDER_PAID).order_by(Notification.id).first()
    response = client.get(f"/bildirimler/{n.id}")
    assert response.status_code == 302 and response.headers["Location"].endswith(f"/uretici/siparisler/{first.id}")
    assert n.is_read and notification_service.unread_count(n.user) == 1

    client.post("/bildirimler/okundu")
    assert notification_service.unread_count(n.user) == 0
    assert "bi-bell-fill" not in client.get("/").get_data(as_text=True)


def test_cannot_open_others_notification_and_no_external_redirect(client):
    listing = setup_listing(client, stock="100", price="10", product_stock="200", min_order="1")
    paid(client, listing, "5")
    n = Notification.query.one()  # üreticinin bildirimi
    assert client.get(f"/bildirimler/{n.id}").status_code == 404  # müşteri açamaz
    n.link = "//kotu-site.example/oltalama"
    db.session.commit()
    login(client, PRODUCER)
    response = client.get(f"/bildirimler/{n.id}")
    assert response.headers["Location"].endswith("/bildirimler")  # dış adrese gitmez


def test_notifications_require_login(client):
    assert client.get("/bildirimler").status_code == 302
    register_and_login(client, "yeni@test.com", role="customer")
    assert "Henüz bildirim yok" in client.get("/bildirimler").get_data(as_text=True)
