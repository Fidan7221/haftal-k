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
    return render_template("main/index.html")


@main_bp.route("/panel")
@login_required
def dashboard():
    """Kullanıcıyı rolüne uygun panele yönlendirir."""
    if current_user.is_producer:
        return redirect(url_for("main.producer_dashboard"))
    if current_user.is_admin:
        return redirect(url_for("main.admin_dashboard"))
    return redirect(url_for("main.customer_dashboard"))


@main_bp.route("/uretici/panel")
@role_required(RoleName.PRODUCER)
def producer_dashboard():
    return render_template("producer/dashboard.html", profile=current_user.producer_profile)


@main_bp.route("/musteri/panel")
@role_required(RoleName.CUSTOMER)
def customer_dashboard():
    return render_template("customer/dashboard.html")


@main_bp.route("/yonetici/panel")
@role_required(RoleName.ADMIN)
def admin_dashboard():
    return render_template("admin/dashboard.html")
