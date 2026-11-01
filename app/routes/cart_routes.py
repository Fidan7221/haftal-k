"""Sepet ve ödeme (checkout) rotaları (Hafta 7). Yalnızca müşteriler kullanır."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.shop_forms import ActionForm, AddToCartForm, CartItemForm, CheckoutForm
from app.models import RoleName
from app.services import cart_service, listing_service, order_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

cart_bp = Blueprint("cart", __name__, url_prefix="/sepet")


@cart_bp.app_context_processor
def inject_cart_count():
    """Gezinme çubuğundaki sepet rozetindeki sayı."""
    if current_user.is_authenticated and current_user.is_customer:
        return {"cart_count": cart_service.item_count(current_user)}
    return {"cart_count": 0}


@cart_bp.route("/")
@role_required(RoleName.CUSTOMER)
def view():
    return render_template("cart/view.html", item_form=CartItemForm(), action_form=ActionForm(),
                           **cart_service.cart_summary(current_user))


@cart_bp.route("/ekle/<int:listing_id>", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def add(listing_id):
    listing = listing_service.get_listing(listing_id)
    if listing is None:
        abort(404)
    form = AddToCartForm()
    if not form.validate_on_submit():
        flash(form.quantity.errors[0] if form.quantity.errors else "Geçerli bir miktar girin.", "danger")
        return redirect(url_for("listing.detail", listing_id=listing.id))
    try:
        cart_service.add_to_cart(current_user, listing, form.quantity.data)
    except ServiceError as error:
        flash(error.message, "danger")
        return redirect(url_for("listing.detail", listing_id=listing.id))
    flash(f"'{listing.title}' sepetinize eklendi.", "success")
    return redirect(url_for("cart.view"))


def _owned_item_or_404(item_id):
    item = cart_service.get_owned_item(current_user, item_id)  # başkasının kalemi -> 404
    if item is None:
        abort(404)
    return item


@cart_bp.route("/kalem/<int:item_id>/guncelle", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def update_item(item_id):
    item = _owned_item_or_404(item_id)
    form = CartItemForm()
    if not form.validate_on_submit():
        flash(form.quantity.errors[0] if form.quantity.errors else "Geçerli bir miktar girin.", "danger")
        return redirect(url_for("cart.view"))
    try:
        cart_service.update_item(item, form.quantity.data)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash("Sepetiniz güncellendi.", "success")
    return redirect(url_for("cart.view"))


@cart_bp.route("/kalem/<int:item_id>/sil", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def remove_item(item_id):
    item = _owned_item_or_404(item_id)
    if not ActionForm().validate_on_submit():
        abort(400)
    cart_service.remove_item(item)
    flash("Ürün sepetten çıkarıldı.", "info")
    return redirect(url_for("cart.view"))


@cart_bp.route("/odeme", methods=["GET", "POST"])
@role_required(RoleName.CUSTOMER)
def checkout():
    summary = cart_service.cart_summary(current_user)
    if not summary["items"]:
        flash("Sepetiniz boş.", "info")
        return redirect(url_for("listing.index"))

    form = CheckoutForm()
    if request.method == "GET" and current_user.address:
        form.shipping_address.data = current_user.address

    if form.validate_on_submit():
        try:
            orders = order_service.checkout(current_user, form.shipping_address.data, form.note.data)
        except ServiceError as error:
            show_service_error(form, error)
        else:
            if len(orders) == 1:
                flash("Siparişiniz oluşturuldu. Ödemeyi tamamlayabilirsiniz.", "success")
                return redirect(url_for("order.customer_detail", order_id=orders[0].id))
            flash(f"Sepetiniz {len(orders)} üreticiye ait olduğu için {len(orders)} ayrı sipariş "
                  "oluşturuldu.", "success")
            return redirect(url_for("order.customer_list"))

    return render_template("cart/checkout.html", form=form, **summary)
