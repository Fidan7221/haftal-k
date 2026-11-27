"""Satış raporu ve bildirim rotaları (Hafta 12).

/uretici/rapor[.csv]     Üretici: kendi satışları        ?gun=7|30|90
/yonetici/rapor[.csv]    Yönetici: tüm platform
/bildirimler             Giriş yapmış herkes: kendi bildirimleri
"""
import csv
import io

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.shop_forms import ActionForm
from app.models import RoleName
from app.services import notification_service, report_service
from app.utils.decorators import role_required

report_bp = Blueprint("report", __name__)


def _days():
    try:
        return int(request.args.get("gun", 30))
    except ValueError:
        return 30


def _render(producer_id, admin_view):
    report = report_service.sales_report(producer_id, _days())
    return render_template("reports/sales.html", report=report, admin_view=admin_view,
                           summary=report_service.summary_text(report),
                           chart=report_service.bar_chart(report.daily), periods=report_service.PERIODS)


def _csv(producer_id, filename):
    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM: Excel Türkçe karakterleri (ş, ğ, ı) doğru açsın
    writer = csv.writer(buffer, delimiter=";")  # Türkçe Excel ondalıkta virgül kullandığı için ayraç ;
    writer.writerows(report_service.csv_rows(producer_id, _days()))
    return Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}-{_days()}gun.csv"})


def _producer_id():
    profile = current_user.producer_profile
    if profile is None:
        abort(404)
    return profile.id


@report_bp.route("/uretici/rapor")
@role_required(RoleName.PRODUCER)
def producer_report():
    return _render(_producer_id(), admin_view=False)


@report_bp.route("/uretici/rapor.csv")
@role_required(RoleName.PRODUCER)
def producer_report_csv():
    return _csv(_producer_id(), "satis-raporu")


@report_bp.route("/yonetici/rapor")
@role_required(RoleName.ADMIN)
def admin_report():
    return _render(None, admin_view=True)


@report_bp.route("/yonetici/rapor.csv")
@role_required(RoleName.ADMIN)
def admin_report_csv():
    return _csv(None, "platform-satis-raporu")


# --- Bildirimler ------------------------------------------------------------------------------

@report_bp.app_context_processor
def inject_notification_count():
    """Menüdeki zil simgesinin üstündeki okunmamış bildirim sayısı."""
    if current_user.is_authenticated:
        return {"notification_count": notification_service.unread_count(current_user)}
    return {"notification_count": 0}


@report_bp.route("/bildirimler")
@login_required
def notifications():
    return render_template("notifications/list.html", notifications=notification_service.list_for(current_user),
                           action_form=ActionForm())


@report_bp.route("/bildirimler/<int:notification_id>")
@login_required
def open_notification(notification_id):
    notification = notification_service.get_own(current_user, notification_id)
    if notification is None:
        abort(404)  # başkasının bildirimi
    notification_service.mark_read(notification)
    link = notification.link or ""
    # Yalnızca site içi adrese git ("/..." ama "//başka-site" değil): açık yönlendirme açığı olmasın
    if link.startswith("/") and not link.startswith("//"):
        return redirect(link)
    return redirect(url_for("report.notifications"))


@report_bp.route("/bildirimler/okundu", methods=["POST"])
@login_required
def mark_all_read():
    if not ActionForm().validate_on_submit():
        abort(400)
    notification_service.mark_all_read(current_user)
    return redirect(url_for("report.notifications"))
