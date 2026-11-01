"""Genel sayfalar ve role göre paneller.

Paneller şimdilik basit; içerikleri sonraki haftalarda dolacak.
Bu hafta amacımız @role_required dekoratörünün çalıştığını göstermek.
"""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models import RoleName
from app.utils.decorators import role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    from app.services.listing_service import latest_listings
    return render_template("main/index.html", latest_listings=latest_listings())


@main_bp.route("/panel")
@login_required
def dashboard():
    """Kullanıcıyı rolüne uygun panele yönlendirir."""
    if current_user.is_producer:
        return redirect(url_for("producer.dashboard"))  # Hafta 6: producer_routes.py'ye taşındı
    if current_user.is_admin:
        return redirect(url_for("main.admin_dashboard"))
    return redirect(url_for("main.customer_dashboard"))


@main_bp.route("/musteri/panel")
@role_required(RoleName.CUSTOMER)
def customer_dashboard():
    from app.services import cart_service, order_service
    orders = order_service.customer_orders(current_user)
    return render_template("customer/dashboard.html", recent_orders=orders[:5],
                           cart_count=cart_service.item_count(current_user))


@main_bp.route("/yonetici/panel")
@role_required(RoleName.ADMIN)
def admin_dashboard():
    return render_template("admin/dashboard.html")
