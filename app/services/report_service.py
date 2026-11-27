"""Satış raporu (Hafta 12).

METRİKLER VE NEDENLERİ
  Ciro             : Ödemesi alınmış siparişlerin (ödendi / kargoda / teslim) kalem tutarları toplamı.
                     Bekleyen sipariş para getirmemiştir, iptal edilen iade edilmiştir; ikisi de SAYILMAZ.
                     (Yönetici panelindeki Hafta 8 ciro hesabıyla aynı kural -> iki ekran tutarlı.)
  Sipariş sayısı   : Ciroya giren sipariş sayısı.
  Ortalama sipariş : Ciro / sipariş sayısı (sipariş yoksa gösterilmez; 0'a bölme yok).
  İptal oranı      : İptal / (satış + iptal). Bekleyenler henüz sonuçlanmadığı için paydada yok.
  Satılan miktar   : BİRİME GÖRE ayrı (kg ile adet toplanamaz: yanlış toplulaştırma olurdu).
  En çok satanlar  : Ürün başına ciro (miktar değil; birimler farklı olduğu için ciro karşılaştırılabilir).
  Önceki dönem     : Aynı uzunluktaki bir önceki dönemle yüzde değişim. Önceki dönemde satış yoksa
                     yüzde hesaplanmaz ("—"); 0'dan büyüme sonsuz % gibi yanıltıcı bir sayı vermez.

TOPLULAŞTIRMA
  Toplamlar ve "en çok satanlar" SQL'de GROUP BY ile hesaplanır (veri tabanında; az satır taşınır).
  Günlük seri Python'da: günler TÜRKİYE SAATİNE göre ayrılır (kayıtlar UTC). UTC ile gruplasaydık
  gece 00:00-03:00 arasındaki satışlar bir önceki güne yazılırdı. Satış olmayan günler 0 olarak
  eklenir (eksik gün atlanırsa grafik yanıltır: boşluk görünmez, eğilim olduğundan farklı görünür).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Order, OrderItem, OrderStatus, ProducerProfile, Product, Listing

SALE_STATUSES = (OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
TR = timezone(timedelta(hours=3), "TRT")  # Türkiye 2016'dan beri yaz saati uygulamıyor: sabit UTC+3
PERIODS = (7, 30, 90)
ZERO = Decimal("0")


@dataclass
class Totals:
    revenue: Decimal = ZERO
    orders: int = 0
    cancelled: int = 0
    pending: int = 0
    pending_amount: Decimal = ZERO

    @property
    def avg_order(self):
        return self.revenue / self.orders if self.orders else None

    @property
    def cancel_rate(self):
        decided = self.orders + self.cancelled
        return self.cancelled / decided * 100 if decided else None


@dataclass
class SalesReport:
    days: int
    start: datetime
    end: datetime
    current: Totals
    previous: Totals
    by_unit: list = field(default_factory=list)       # [(birim, miktar)]
    top_products: list = field(default_factory=list)  # [{"name","unit","quantity","revenue"}]
    daily: list = field(default_factory=list)         # [(tarih, ciro)] her gün, satışsız gün 0
    by_producer: list = field(default_factory=list)   # yalnızca yönetici: [(çiftlik, ciro)]

    @property
    def last_day(self):
        return (self.end - timedelta(days=1)).date()

    @property
    def revenue_change(self):
        return _change(self.current.revenue, self.previous.revenue)

    @property
    def orders_change(self):
        return _change(self.current.orders, self.previous.orders)

    @property
    def has_data(self):
        return bool(self.current.orders or self.current.cancelled or self.current.pending)


def _change(now, before):
    if not before:
        return None  # önceki dönemde hiç yoksa yüzde anlamsız
    return float((Decimal(now) - Decimal(before)) / Decimal(before) * 100)


def _base(producer_id, start, end):
    """Dönem ve (varsa) üretici filtresi uygulanmış OrderItem + Order birleşimi."""
    stmt = (db.select().select_from(OrderItem).join(Order, OrderItem.order_id == Order.id)
            .where(Order.created_at >= start, Order.created_at < end))
    if producer_id is not None:
        stmt = stmt.where(OrderItem.producer_id == producer_id)
    return stmt


LINE_TOTAL = OrderItem.quantity * OrderItem.unit_price


def _totals(producer_id, start, end):
    # SELECT orders.status, COUNT(DISTINCT orders.id), SUM(qty * unit_price) ... GROUP BY orders.status
    rows = db.session.execute(
        _base(producer_id, start, end)
        .add_columns(Order.status, func.count(func.distinct(Order.id)), func.coalesce(func.sum(LINE_TOTAL), 0))
        .group_by(Order.status)
    ).all()
    totals = Totals()
    for status, count, amount in rows:
        amount = Decimal(amount)
        if status in SALE_STATUSES:
            totals.revenue += amount
            totals.orders += count
        elif status == OrderStatus.CANCELLED:
            totals.cancelled += count
        elif status == OrderStatus.PENDING:
            totals.pending += count
            totals.pending_amount += amount
    return totals


def period(days=30, now=None):
    """(gün sayısı, başlangıç, bitiş) — Türkiye saatiyle bugünün sonunda biten tam günler."""
    days = days if days in PERIODS else 30
    now = now or datetime.now(timezone.utc)
    end_local = datetime.combine(now.astimezone(TR).date() + timedelta(days=1), datetime.min.time(), TR)
    return days, end_local - timedelta(days=days), end_local


def sales_report(producer_id=None, days=30, now=None):
    """producer_id=None -> tüm platform (yönetici)."""
    days, start_local, end_local = period(days, now)
    start, end = start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
    prev_start = start - timedelta(days=days)

    report = SalesReport(days, start_local, end_local, _totals(producer_id, start, end),
                         _totals(producer_id, prev_start, start))
    sale = Order.status.in_(SALE_STATUSES)

    # Birime göre satılan miktar
    report.by_unit = [(unit, Decimal(qty)) for unit, qty in db.session.execute(
        _base(producer_id, start, end).join(Listing, OrderItem.listing_id == Listing.id)
        .join(Product, Listing.product_id == Product.id)
        .add_columns(Product.unit, func.sum(OrderItem.quantity)).where(sale)
        .group_by(Product.unit).order_by(Product.unit)).all()]

    # En çok satan 5 ürün (ciroya göre)
    report.top_products = [
        {"name": name, "unit": unit, "quantity": Decimal(qty), "revenue": Decimal(rev)}
        for name, unit, qty, rev in db.session.execute(
            _base(producer_id, start, end).join(Listing, OrderItem.listing_id == Listing.id)
            .join(Product, Listing.product_id == Product.id)
            .add_columns(Product.name, Product.unit, func.sum(OrderItem.quantity), func.sum(LINE_TOTAL))
            .where(sale).group_by(Product.id, Product.name, Product.unit)
            .order_by(func.sum(LINE_TOTAL).desc()).limit(5)).all()]

    # Günlük seri (Türkiye günü), satışsız günler 0
    buckets = defaultdict(lambda: ZERO)
    for created_at, line in db.session.execute(
            _base(producer_id, start, end).add_columns(Order.created_at, LINE_TOTAL).where(sale)).all():
        if created_at.tzinfo is None:  # SQLite saat dilimini saklamaz; değer UTC'dir
            created_at = created_at.replace(tzinfo=timezone.utc)
        buckets[created_at.astimezone(TR).date()] += Decimal(line)
    first = start_local.date()
    report.daily = [(first + timedelta(days=i), buckets[first + timedelta(days=i)]) for i in range(days)]

    if producer_id is None:  # yönetici: üreticiye göre ciro
        report.by_producer = [(farm, Decimal(rev)) for farm, rev in db.session.execute(
            _base(None, start, end).join(ProducerProfile, OrderItem.producer_id == ProducerProfile.id)
            .add_columns(ProducerProfile.farm_name, func.sum(LINE_TOTAL)).where(sale)
            .group_by(ProducerProfile.id, ProducerProfile.farm_name)
            .order_by(func.sum(LINE_TOTAL).desc())).all()]
    return report


def summary_text(report):
    """Raporun tek paragraflık Türkçe özeti (kural tabanlı; sayılar rapordan gelir)."""
    c = report.current
    if not report.has_data:
        return f"Son {report.days} günde sipariş yok."
    parts = [f"Son {report.days} günde {c.orders} siparişten {_tl(c.revenue)} ciro elde edildi"]
    if report.revenue_change is not None:
        direction = "arttı" if report.revenue_change >= 0 else "azaldı"
        parts[0] += f"; ciro önceki {report.days} güne göre %{abs(report.revenue_change):.0f} {direction}"
    parts[0] += "."
    if report.top_products:
        best = report.top_products[0]
        parts.append(f"En çok ciro getiren ürün: {best['name']} ({_tl(best['revenue'])}).")
    if c.cancelled:
        parts.append(f"{c.cancelled} sipariş iptal edildi (iptal oranı %{c.cancel_rate:.0f}).")
    if c.pending:
        parts.append(f"{c.pending} sipariş ödeme bekliyor ({_tl(c.pending_amount)}); bu tutar ciroya dahil değil.")
    return " ".join(parts)


def _tl(value):
    text = f"{Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} TL"


def bar_chart(daily, width=640, height=180, pad_left=48, pad_bottom=22, pad_top=8):
    """Günlük ciro için SVG çubuk grafik ölçüleri. Y ekseni HER ZAMAN 0'dan başlar
    (0'dan başlamayan eksen küçük farkları büyük gösterir: yanıltıcı görsel)."""
    values = [float(v) for _, v in daily]
    top = max(values) if values and max(values) > 0 else 1.0
    plot_w, plot_h = width - pad_left - 4, height - pad_bottom - pad_top
    slot = plot_w / max(len(values), 1)
    bar_w = max(slot * 0.7, 1.5)
    bars = []
    for i, (day, value) in enumerate(daily):
        h = float(value) / top * plot_h
        bars.append({"x": round(pad_left + i * slot + (slot - bar_w) / 2, 1), "y": round(pad_top + plot_h - h, 1),
                     "w": round(bar_w, 1), "h": round(h, 1), "day": day, "value": value,
                     "label": day.strftime("%d.%m") if (i % max(len(values) // 6, 1) == 0) else None})
    grid = [{"y": round(pad_top + plot_h - plot_h * f, 1), "label": _tl(Decimal(str(top * f))).replace(" TL", "")}
            for f in (0, 0.5, 1)]
    return {"width": width, "height": height, "bars": bars, "grid": grid, "pad_left": pad_left,
            "base_y": pad_top + plot_h}


# --- CSV dışa aktarma -------------------------------------------------------------------------------

def _safe_cell(value):
    """CSV/formül enjeksiyonu: '=', '+', '-', '@' ile başlayan hücreyi Excel formül sanıp çalıştırır.
    Başına ' eklenerek düz metin yapılır (ürün adı kullanıcıdan geldiği için gerekli)."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def csv_rows(producer_id=None, days=30, now=None):
    """Dönemdeki TÜM sipariş kalemleri (durum sütunuyla; rapordaki ciro yalnızca satış durumlarını sayar)."""
    _, start_local, end_local = period(days, now)
    start, end = start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
    rows = db.session.execute(
        _base(producer_id, start, end).join(Listing, OrderItem.listing_id == Listing.id)
        .join(Product, Listing.product_id == Product.id)
        .join(ProducerProfile, OrderItem.producer_id == ProducerProfile.id)
        .add_columns(Order.id, Order.created_at, Order.status, ProducerProfile.farm_name, Product.name,
                     OrderItem.quantity, Product.unit, OrderItem.unit_price)
        .order_by(Order.created_at, Order.id)).all()
    header = ["Sipariş no", "Tarih", "Durum", "Ciroya dahil"] + (["Üretici"] if producer_id is None else []) + \
             ["Ürün", "Miktar", "Birim", "Birim fiyat (TL)", "Tutar (TL)"]
    yield header
    for order_id, created_at, status, farm, name, qty, unit, price in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        dec = lambda v: f"{Decimal(v):.2f}".replace(".", ",")  # Türkçe Excel: ondalık virgül
        row = [order_id, created_at.astimezone(TR).strftime("%d.%m.%Y %H:%M"),
               OrderStatus.LABELS.get(status, status), "Evet" if status in SALE_STATUSES else "Hayır"]
        if producer_id is None:
            row.append(_safe_cell(farm))
        row += [_safe_cell(name), dec(qty), unit, dec(price), dec(Decimal(qty) * Decimal(price))]
        yield row
