"""Canlı sunum için sentetik demo verisi (Hafta 7).

Çalıştırma: flask seed-demo   (Render'da başlatma komutunun içinde otomatik çalışır)

KVKK: Buradaki kişi ve çiftlik adları UYDURMADIR. E-postalar "example.com" alan
adındadır; bu alan adı RFC 2606 ile örnekler için ayrılmıştır, gerçek bir kişiye ait
olamaz. Telefon, TC kimlik, gerçek adres gibi kişisel veri YOKTUR.

Güvenlik: Demo hesapların parolası koda yazılmaz; DEMO_PASSWORD ortam değişkeninden
okunur. Değişken tanımlı değilse hiçbir şey eklenmez.
"""
import os
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (
    Category, Listing, ListingStatus, ProducerProfile, Product, Role, RoleName, Unit, User,
)

# (e-posta, ad soyad, çiftlik, bölge, [(ürün, kategori slug, birim, depo stoğu, ilan fiyatı, ilana ayrılan, en az, organik)])
PRODUCERS = [
    ("uretici1@example.com", "Demo Üretici Bir", "Yeşil Vadi Çiftliği", "Bingöl / Merkez", [
        ("Salkım Domates", "domates", Unit.KG, "300", "32.50", "120", "2", True),
        ("Kapya Biber", "biber", Unit.KG, "150", "45.00", "60", "1", False),
        ("Çiçek Balı", "cicek-bali", Unit.PIECE, "40", "650.00", "20", "1", True),
    ]),
    ("uretici2@example.com", "Demo Üretici İki", "Dağ Eteği Gıda", "Bingöl / Genç", [
        ("Gün Kurusu Kayısı", "kayisi", Unit.KG, "80", "210.00", "50", "1", True),
        ("Köy Tereyağı", "tereyagi", Unit.KG, "30", "520.00", "15", "1", False),
        ("Kuru Fasulye", "fasulye", Unit.KG, "200", "95.00", "100", "2", False),
    ]),
]

CUSTOMER = ("musteri@example.com", "Demo Müşteri")
# Hafta 8: Vize demosunda yönetici panelini canlıda gösterebilmek için. Ücretsiz Render
# planında terminal (shell) olmadığı için "flask create-admin" canlıda çalıştırılamıyor.
# Parolası da DEMO_PASSWORD'dür (koda yazılmaz).
ADMIN = ("yonetici@example.com", "Demo Yönetici")


def _user(email, full_name, role_name, password):
    user = User.query.filter_by(email=email).first()
    if user:
        return user, False
    user = User(email=email, full_name=full_name, role=Role.query.filter_by(name=role_name).one())
    user.set_password(password)
    db.session.add(user)
    return user, True


def seed_demo():
    password = os.environ.get("DEMO_PASSWORD", "").strip()
    if not password:
        return "DEMO_PASSWORD tanımlı değil; demo verisi eklenmedi."
    if len(password) < 8:
        return "DEMO_PASSWORD en az 8 karakter olmalı; demo verisi eklenmedi."

    created = 0
    for email, full_name, farm, region, products in PRODUCERS:
        user, is_new = _user(email, full_name, RoleName.PRODUCER, password)
        if not is_new:
            continue  # daha önce eklenmiş: tekrar ekleme (komut her açılışta çalışabilir)
        profile = ProducerProfile(user=user, farm_name=farm, region=region, is_verified=True)
        db.session.add(profile)
        for name, slug, unit, stock, price, listed, min_order, organic in products:
            product = Product(producer=profile, category=Category.query.filter_by(slug=slug).one(),
                              name=name, unit=unit, stock_quantity=Decimal(stock), is_organic=organic,
                              description="Demo ürün (sentetik veri).")
            db.session.add(product)
            db.session.add(Listing(product=product, title=name, price=Decimal(price),
                                   stock_quantity=Decimal(listed), min_order_quantity=Decimal(min_order),
                                   end_date=date.today() + timedelta(days=90),
                                   status=ListingStatus.ACTIVE))
        created += 1

    _, customer_new = _user(*CUSTOMER, RoleName.CUSTOMER, password)
    _, admin_new = _user(*ADMIN, RoleName.ADMIN, password)
    db.session.commit()
    if not created and not customer_new and not admin_new:
        return "Demo verisi zaten var; değişiklik yapılmadı."
    return (f"Demo verisi eklendi: {created} üretici, {1 if customer_new else 0} müşteri, "
            f"{1 if admin_new else 0} yönetici.")
