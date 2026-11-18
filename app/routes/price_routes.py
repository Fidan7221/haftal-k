"""Hal fiyatları (Hafta 9) ve yapay zekâ satış zamanı önerisi (Hafta 10).

/hal-fiyatlari                              Herkese açık: son hal fiyatları ve haftalık değişim
/uretici/urunler/<id>/fiyat-onerisi         Üretici: ürünü için trend + satış zamanı önerisi
"""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.forms.shop_forms import ActionForm
from app.models import RoleName
from app.services import ai_service, price_service, producer_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required

price_bp = Blueprint("price", __name__)


@price_bp.route("/hal-fiyatlari")
def index():
    latest_day, rows = price_service.latest_prices()
    return render_template("prices/index.html", latest_day=latest_day, rows=rows,
                           sample_data=price_service.is_sample_data())


def _owned_product_or_404(product_id):
    profile = current_user.producer_profile
    product = producer_service.get_owned_product(profile, product_id) if profile else None
    if product is None:
        abort(404)  # başka üreticinin ürünü
    return product


@price_bp.route("/uretici/urunler/<int:product_id>/fiyat-onerisi", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def suggestion(product_id):
    product = _owned_product_or_404(product_id)
    form = ActionForm()
    refresh = form.validate_on_submit()  # POST + geçerli CSRF = "Yeniden hesapla"
    try:
        result = ai_service.suggest_for_product(product, refresh=refresh)
    except ServiceError as error:
        if refresh:
            flash(error.message, "warning")
            return redirect(url_for("price.suggestion", product_id=product.id))
        return render_template("prices/suggestion.html", product=product, result=None,
                               error=error.message, form=form, ai_status=ai_service.ai_status())
    if refresh:
        # Yönlendirmeden sonra kaybolmasınlar diye notlar flash ile taşınır
        for note in result.notes:
            flash(note, "info")
        for warning in result.warnings:
            flash(warning, "warning")
        flash("Öneri yeniden hesaplandı.", "success")
        return redirect(url_for("price.suggestion", product_id=product.id))  # yenilemede tekrar POST olmasın
    return render_template("prices/suggestion.html", product=product, result=result, error=None,
                           form=form, ai_status=ai_service.ai_status(),
                           points=ai_service.chart_points(result.series))
