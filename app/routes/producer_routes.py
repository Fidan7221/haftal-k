"""Üretici rotaları (Hafta 6): panel, profil ve ürün yönetimi.

Bu Blueprint'teki her sayfa @role_required(RoleName.PRODUCER) ile korunur.
Sahiplik kontrolü: başka üreticinin ürün id'si yazılırsa 404 döner; böylece
o id'de bir ürün olup olmadığı bile belli olmaz.
"""
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.producer_forms import DeleteForm, ProducerProfileForm, ProductForm, StockForm
from app.models import RoleName
from app.services import category_service, producer_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

producer_bp = Blueprint("producer", __name__, url_prefix="/uretici")


def _profile():
    profile = current_user.producer_profile
    if profile is None:
        abort(404)
    return profile


def _owned_product_or_404(product_id):
    product = producer_service.get_owned_product(_profile(), product_id)
    if product is None:
        abort(404)
    return product


def _qty(value):
    """Decimal('75.50') -> '75,5' (mesajlarda Türkçe sayı biçimi)."""
    text = f"{Decimal(value).quantize(Decimal('0.01')):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _product_form_kwargs(form):
    return dict(
        category_id=form.category_id.data,
        name=form.name.data,
        unit=form.unit.data,
        stock_quantity=form.stock_quantity.data,
        description=form.description.data,
        is_organic=form.is_organic.data,
        is_active=form.is_active.data,
        image_file=form.image.data,
    )


# --- Panel ve profil ------------------------------------------------------

@producer_bp.route("/panel")
@role_required(RoleName.PRODUCER)
def dashboard():
    profile = _profile()
    return render_template("producer/dashboard.html", profile=profile,
                           **producer_service.dashboard_data(profile))


@producer_bp.route("/profil", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_profile():
    profile = _profile()
    form = ProducerProfileForm()

    if request.method == "GET":
        # Formu mevcut bilgilerle doldur (iki farklı tablodan)
        form.full_name.data = current_user.full_name
        form.phone.data = current_user.phone
        form.city.data = current_user.city
        form.farm_name.data = profile.farm_name
        form.region.data = profile.region
        form.tax_number.data = profile.tax_number
        form.description.data = profile.description

    if form.validate_on_submit():
        try:
            producer_service.update_profile(
                current_user,
                full_name=form.full_name.data, phone=form.phone.data, city=form.city.data,
                farm_name=form.farm_name.data, region=form.region.data,
                description=form.description.data, tax_number=form.tax_number.data,
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash("Profiliniz güncellendi.", "success")
            return redirect(url_for("producer.dashboard"))

    return render_template("producer/profile.html", form=form, profile=profile)


# --- Ürünler (CRUD) -------------------------------------------------------

@producer_bp.route("/urunler")
@role_required(RoleName.PRODUCER)
def products():
    page = request.args.get("sayfa", 1, type=int)
    search = request.args.get("q", "")
    category_id = request.args.get("kategori", 0, type=int) or None

    pagination = producer_service.list_products(_profile(), search, category_id, page)
    return render_template(
        "producer/products.html",
        pagination=pagination,
        search=search,
        category_id=category_id,
        category_groups=category_service.product_category_choices(),
        delete_form=DeleteForm(),
        stock_form=StockForm(),
    )


@producer_bp.route("/urunler/yeni", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def new_product():
    form = ProductForm()
    form.category_id.choices = category_service.product_category_choices()

    if form.validate_on_submit():
        try:
            product = producer_service.create_product(_profile(), **_product_form_kwargs(form))
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{product.name}' ürününüz eklendi.", "success")
            return redirect(url_for("producer.products"))

    return render_template("producer/product_form.html", form=form, product=None)


@producer_bp.route("/urunler/<int:product_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_product(product_id):
    product = _owned_product_or_404(product_id)
    form = ProductForm(obj=product)  # GET isteğinde alanları ürün bilgileriyle doldurur
    form.category_id.choices = category_service.product_category_choices()

    if form.validate_on_submit():
        try:
            producer_service.update_product(
                product, remove_image=form.remove_image.data, **_product_form_kwargs(form)
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{product.name}' güncellendi.", "success")
            return redirect(url_for("producer.products"))

    return render_template("producer/product_form.html", form=form, product=product)


@producer_bp.route("/urunler/<int:product_id>/stok", methods=["POST"])
@role_required(RoleName.PRODUCER)
def update_stock(product_id):
    product = _owned_product_or_404(product_id)  # başkasının ürünü -> 404
    form = StockForm()
    if not form.validate_on_submit():
        message = form.quantity.errors[0] if form.quantity.errors else "Geçerli bir stok miktarı girin."
        flash(message, "danger")
        return redirect(url_for("producer.products"))

    try:
        producer_service.update_stock(product, form.quantity.data)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"'{product.name}' stoğu {_qty(product.stock_quantity)} {product.unit} olarak güncellendi.",
              "success")
    return redirect(url_for("producer.products"))


@producer_bp.route("/urunler/<int:product_id>/sil", methods=["POST"])
@role_required(RoleName.PRODUCER)
def delete_product(product_id):
    product = _owned_product_or_404(product_id)
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)

    name = product.name
    result = producer_service.delete_product(product)
    if result == "archived":
        flash(f"'{name}' geçmiş siparişlerde kullanıldığı için silinmedi, arşive alındı "
              "(satışa kapatıldı).", "warning")
    else:
        flash(f"'{name}' silindi.", "success")
    return redirect(url_for("producer.products"))
