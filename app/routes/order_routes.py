"""Sipariş rotaları (Hafta 7).

Müşteri: /siparislerim               (kendi siparişleri)
Üretici: /uretici/siparisler         (kendi ürünlerinin siparişleri)
Durum değişikliği: POST /siparis/<id>/durum  (kim neyi yapabilir -> order_service.TRANSITIONS)
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.shop_forms import OrderStatusForm
from app.models import OrderStatus, RoleName
from app.repositories.order_repository import OrderRepository
from app.services import order_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required

order_bp = Blueprint("order", __name__)


@order_bp.route("/siparislerim")
@role_required(RoleName.CUSTOMER)
def customer_list():
    return render_template("orders/list.html", orders=order_service.customer_orders(current_user),
                           producer_view=False, status_filter=None, statuses=OrderStatus)


@order_bp.route("/siparislerim/<int:order_id>")
@role_required(RoleName.CUSTOMER)
def customer_detail(order_id):
    order = order_service.get_customer_order(current_user, order_id)
    if order is None:
        abort(404)  # başkasının siparişi
    return _render_detail(order, producer_view=False)


@order_bp.route("/uretici/siparisler")
@role_required(RoleName.PRODUCER)
def producer_list():
    profile = current_user.producer_profile
    status = request.args.get("durum")
    if status not in OrderStatus.ALL:
        status = None
    return render_template("orders/list.html", orders=order_service.producer_orders(profile, status),
                           producer_view=True, status_filter=status, statuses=OrderStatus)


@order_bp.route("/uretici/siparisler/<int:order_id>")
@role_required(RoleName.PRODUCER)
def producer_detail(order_id):
    order = order_service.get_producer_order(current_user.producer_profile, order_id)
    if order is None:
        abort(404)
    return _render_detail(order, producer_view=True)


def _render_detail(order, producer_view):
    return render_template("orders/detail.html", order=order, producer_view=producer_view,
                           actions=order_service.allowed_actions(current_user, order),
                           status_form=OrderStatusForm(), statuses=OrderStatus)


@order_bp.route("/siparis/<int:order_id>/durum", methods=["POST"])
@login_required
def change_status(order_id):
    order = OrderRepository.get_by_id(order_id)
    if order is None or order_service.actor_role(current_user, order) is None:
        abort(404)  # sipariş yok ya da kullanıcının bu siparişle ilgisi yok

    form = OrderStatusForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        order_service.change_status(current_user, order, form.new_status.data)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"Sipariş #{order.id} durumu: {order.status_label}", "success")

    if order_service.actor_role(current_user, order) == order_service.PRODUCER:
        return redirect(url_for("order.producer_detail", order_id=order.id))
    if current_user.is_customer:
        return redirect(url_for("order.customer_detail", order_id=order.id))
    # Hafta 8: Yönetici önceden panele atılıyordu; artık işlem yaptığı siparişe döner
    return redirect(url_for("admin.order_detail", order_id=order.id))
