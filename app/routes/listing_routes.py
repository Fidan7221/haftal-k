"""İlan rotaları (Hafta 7).

Herkese açık:  /ilanlar (vitrin), /ilanlar/<id> (detay + sepete ekle formu)
Üretici:       /uretici/ilanlar ... (kendi ilanlarını yönetir)

Sahiplik kontrolü: başka üreticinin ilan id'si yazılırsa 404 döner.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.shop_forms import AddToCartForm, ActionForm, ListingForm
from app.models import RoleName
from app.services import category_service, listing_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

listing_bp = Blueprint("listing", __name__)


# --- Vitrin (herkese açık) ---------------------------------------------------

@listing_bp.route("/ilanlar")
def index():
    page = request.args.get("sayfa", 1, type=int)
    search = request.args.get("q", "")
    category_id = request.args.get("kategori", 0, type=int) or None
    return render_template(
        "listings/index.html",
        pagination=listing_service.public_listings(search, category_id, page),
        search=search,
        category_id=category_id,
        categories=category_service.category_tree(),
    )


@listing_bp.route("/ilanlar/<int:listing_id>")
def detail(listing_id):
    listing = listing_service.get_listing(listing_id)
    if listing is None:
        abort(404)
    form = AddToCartForm(quantity=listing.min_order_quantity)
    return render_template("listings/detail.html", listing=listing, form=form)


# --- Üretici ilan yönetimi ----------------------------------------------------

def _profile():
    profile = current_user.producer_profile
    if profile is None:
        abort(404)
    return profile


def _owned_listing_or_404(listing_id):
    listing = listing_service.get_owned_listing(_profile(), listing_id)
    if listing is None:
        abort(404)
    return listing


@listing_bp.route("/uretici/ilanlar")
@role_required(RoleName.PRODUCER)
def my_listings():
    return render_template("producer/listings.html",
                           listings=listing_service.producer_listings(_profile()),
                           action_form=ActionForm())


@listing_bp.route("/uretici/ilanlar/yeni", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def new_listing():
    profile = _profile()
    products = listing_service.listable_products(profile)
    if not products:
        flash("İlan açmak için önce satışa açık bir ürün ekleyin.", "warning")
        return redirect(url_for("producer.new_product"))

    form = ListingForm()
    form.product_id.choices = [(p.id, f"{p.name} (depoda {listing_service.free_stock(p).normalize():f} "
                                      f"{p.unit} boşta)") for p in products]
    if request.method == "GET" and request.args.get("urun", type=int):
        form.product_id.data = request.args.get("urun", type=int)

    if form.validate_on_submit():
        try:
            listing = listing_service.create_listing(
                profile, product_id=form.product_id.data, title=form.title.data,
                price=form.price.data, stock_quantity=form.stock_quantity.data,
                min_order_quantity=form.min_order_quantity.data, end_date=form.end_date.data,
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{listing.title}' ilanı yayında.", "success")
            return redirect(url_for("listing.my_listings"))

    return render_template("producer/listing_form.html", form=form, listing=None)


@listing_bp.route("/uretici/ilanlar/<int:listing_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_listing(listing_id):
    listing = _owned_listing_or_404(listing_id)
    form = ListingForm(obj=listing)
    # İlanın ürünü değiştirilemez; açılır listede yalnızca kendi ürünü durur
    form.product_id.choices = [(listing.product.id, listing.product.name)]
    form.product_id.data = listing.product.id

    if form.validate_on_submit():
        try:
            listing_service.update_listing(
                listing, title=form.title.data, price=form.price.data,
                stock_quantity=form.stock_quantity.data,
                min_order_quantity=form.min_order_quantity.data, end_date=form.end_date.data,
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{listing.title}' ilanı güncellendi.", "success")
            return redirect(url_for("listing.my_listings"))

    return render_template("producer/listing_form.html", form=form, listing=listing)


@listing_bp.route("/uretici/ilanlar/<int:listing_id>/<action>", methods=["POST"])
@role_required(RoleName.PRODUCER)
def listing_action(listing_id, action):
    listing = _owned_listing_or_404(listing_id)
    if not ActionForm().validate_on_submit():
        abort(400)

    try:
        if action == "kapat":
            listing_service.close_listing(listing)
            flash(f"'{listing.title}' satışa kapatıldı.", "success")
        elif action == "ac":
            listing_service.reopen_listing(listing)
            flash(f"'{listing.title}' tekrar satışta.", "success")
        elif action == "sil":
            title = listing.title
            if listing_service.delete_listing(listing) == "closed":
                flash(f"'{title}' siparişlerde kullanıldığı için silinmedi, kapatıldı.", "warning")
            else:
                flash(f"'{title}' silindi.", "success")
        else:
            abort(404)
    except ServiceError as error:
        flash(error.message, "danger")
    return redirect(url_for("listing.my_listings"))
