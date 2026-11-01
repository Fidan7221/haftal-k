"""Yönetici rotaları (Hafta 6: kategori yönetimi, Hafta 8: panel özeti ve sipariş takibi)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.admin_forms import CategoryForm
from app.forms.producer_forms import DeleteForm
from app.forms.shop_forms import OrderStatusForm
from app.models import OrderStatus, RoleName
from app.repositories.order_repository import OrderRepository, StatsRepository
from app.repositories.product_repository import CategoryRepository
from app.services import category_service, order_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

admin_bp = Blueprint("admin", __name__, url_prefix="/yonetici")


def _category_or_404(category_id):
    category = CategoryRepository.get_by_id(category_id)
    if category is None:
        abort(404)
    return category


# --- Hafta 8: Panel ve sipariş takibi ----------------------------------------

@admin_bp.route("/panel")
@role_required(RoleName.ADMIN)
def dashboard():
    return render_template("admin/dashboard.html", stats=StatsRepository.get_summary_stats(),
                           recent_orders=StatsRepository.recent_orders(limit=5),
                           statuses=OrderStatus)


@admin_bp.route("/siparisler")
@role_required(RoleName.ADMIN)
def orders():
    status = request.args.get("durum")
    if status not in OrderStatus.ALL:
        status = None
    return render_template("orders/list.html", orders=StatsRepository.recent_orders(limit=200, status=status),
                           producer_view=True, admin_view=True, status_filter=status,
                           statuses=OrderStatus)


@admin_bp.route("/siparisler/<int:order_id>")
@role_required(RoleName.ADMIN)
def order_detail(order_id):
    order = OrderRepository.get_by_id(order_id)
    if order is None:
        abort(404)
    return render_template("orders/detail.html", order=order, producer_view=True, admin_view=True,
                           actions=order_service.allowed_actions(current_user, order),
                           status_form=OrderStatusForm(), statuses=OrderStatus)


# --- Hafta 6: Kategori yönetimi ------------------------------------------------

@admin_bp.route("/kategoriler")
@role_required(RoleName.ADMIN)
def categories():
    return render_template("admin/categories.html",
                           tree=category_service.category_tree(), delete_form=DeleteForm())


@admin_bp.route("/kategoriler/yeni", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def new_category():
    form = CategoryForm()
    form.parent_id.choices = category_service.parent_choices()

    if form.validate_on_submit():
        try:
            category = category_service.create_category(
                form.name.data, form.slug.data, form.parent_id.data or None
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{category.name}' kategorisi eklendi.", "success")
            return redirect(url_for("admin.categories"))

    return render_template("admin/category_form.html", form=form, category=None)


@admin_bp.route("/kategoriler/<int:category_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def edit_category(category_id):
    category = _category_or_404(category_id)
    form = CategoryForm(obj=category)
    form.parent_id.choices = category_service.parent_choices(exclude_id=category.id)
    if form.parent_id.data is None:
        form.parent_id.data = 0  # Ana kategoride parent_id boştur; listede "yok" seçili olsun

    if form.validate_on_submit():
        try:
            category_service.update_category(
                category, form.name.data, form.slug.data, form.parent_id.data or None
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{category.name}' güncellendi.", "success")
            return redirect(url_for("admin.categories"))

    return render_template("admin/category_form.html", form=form, category=category)


@admin_bp.route("/kategoriler/<int:category_id>/sil", methods=["POST"])
@role_required(RoleName.ADMIN)
def delete_category(category_id):
    category = _category_or_404(category_id)
    if not DeleteForm().validate_on_submit():
        abort(400)
    try:
        name = category.name
        category_service.delete_category(category)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"'{name}' kategorisi silindi.", "success")
    return redirect(url_for("admin.categories"))
