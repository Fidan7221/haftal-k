"""Genel sayfalar ve role göre paneller.

Paneller şimdilik basit; içerikleri sonraki haftalarda dolacak.
Bu hafta amacımız @role_required dekoratörünün çalıştığını göstermek.
"""
from flask import Blueprint, abort, current_app, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ProductImage, RoleName
from app.utils.decorators import role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    from app.services.listing_service import latest_listings
    return render_template("main/index.html", latest_listings=latest_listings())


@main_bp.route("/urun-resmi/<int:image_id>")
def product_photo(image_id):
    """Veri tabanındaki ürün fotoğrafını tarayıcıya gönderir (v0.10.4).

    Herkese açık: fotoğraflar zaten Pazar'da herkese görünüyor. Fotoğraf değişince yeni bir
    kayıt (yeni id) oluştuğu için tarayıcı aynı adresi 1 gün önbellekte tutabilir.
    """
    image = db.session.get(ProductImage, image_id)
    if image is None:
        abort(404)
    response = current_app.response_class(image.data, mimetype=image.content_type)
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["X-Content-Type-Options"] = "nosniff"  # tarayıcı türü tahmin etmesin
    return response


@main_bp.route("/panel")
@login_required
def dashboard():
    """Kullanıcıyı rolüne uygun panele yönlendirir."""
    if current_user.is_producer:
        return redirect(url_for("producer.dashboard"))  # Hafta 6: producer_routes.py'ye taşındı
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("main.customer_dashboard"))


@main_bp.route("/musteri/panel")
@role_required(RoleName.CUSTOMER)
def customer_dashboard():
    from app.services import cart_service, order_service
    orders = order_service.customer_orders(current_user)
    return render_template("customer/dashboard.html", recent_orders=orders[:5],
                           cart_count=cart_service.item_count(current_user))


# Yönetici paneli (/yonetici/panel) Hafta 8'de admin_routes.py'ye taşındı (adres aynı kaldı).
