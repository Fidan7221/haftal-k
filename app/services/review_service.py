"""Değerlendirme ve itibar modülü (Hafta 11).

VERİ MODELİ (tablolar Hafta 3'ten beri hazırdı):
    order_items 1 ── 0..1 reviews      (her sipariş kalemine en fazla 1 yorum: UNIQUE order_item_id)
    users       1 ── *    reviews      (yorumu yazan müşteri)
    producer_profiles 1 ── * reviews   (yorumu alan üretici)
    producer_profiles.reputation_score / review_count  -> itibarın ÖNBELLEĞİ (her değişiklikte yeniden hesaplanır)
  Yorum, ürüne doğrudan değil SİPARİŞ KALEMİNE bağlıdır: "satın almadan yorum" yapısal olarak imkânsızdır.

İŞ KURALLARI (can_review -> hepsi sağlanmazsa yorum yapılamaz):
  1) Yalnızca o siparişi veren müşteri yorum yapar (rol + sahiplik).
  2) Sipariş "teslim edildi" olmalı (ürünü almadan değerlendirme olmaz).
  3) Teslimden sonra en fazla REVIEW_WINDOW_DAYS gün içinde.
  4) Her sipariş kalemi için tek yorum (servis kontrol eder, veri tabanı da UNIQUE ile garanti eder).
  5) Puan 1-5 tam sayı (form + servis + veri tabanı CHECK kısıtı).
  6) 1-2 yıldızlı yorumda en az MIN_LOW_RATING_COMMENT karakter açıklama zorunlu
     (gerekçesiz "1 yıldız" ile üreticiyi cezalandırmak zorlaşır, üretici sorunu anlar).

KÖTÜYE KULLANIM ÖNLEME:
  - Doğrulanmış satın alma (kural 1-2): sahte hesapla, alışveriş yapmadan yorum yapılamaz.
  - Günlük sınır: bir müşteri 24 saatte en fazla DAILY_REVIEW_LIMIT yorum.
  - İçerik denetimi: bağlantı (reklam/oltalama), telefon ve e-posta (kişisel veri, KVKK),
    aynı harfin uzun tekrarı ve tamamı büyük harf (spam) reddedilir.
  - Yönetici yorumu gizleyebilir; gizli yorum itibara katılmaz.
  - İtibar hesabında HER MÜŞTERİ BİR OY: aynı müşteri 10 sipariş verip 10 kez 5 yıldız verse de
    itibara tek oy (puanlarının ortalaması) olarak girer. Puan şişirme/batırma zorlaşır.
  - Bayes ortalaması: az oyu olan üreticinin puanı platform ortalamasına çekilir; tek bir
    (belki sahte) 5 yıldız "5,0" itibar yapmaz.

İTİBAR (compute_reputation):
    itibar = (C × m + Σ müşteri_puanları) / (C + müşteri_sayısı)
    C = PRIOR_WEIGHT (güven ağırlığı: "kaç oy görmeden ortalamaya güvenmeyiz"), m = platform ortalaması
    Örnek: m = 4,0, C = 5. Tek müşteri 5 verdi -> (5×4 + 5) / 6 = 4,17 (5,0 değil).
           20 müşteri ortalama 4,8 verdi -> (5×4 + 96) / 25 = 4,64.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.models import OrderStatus, Review
from app.repositories.review_repository import ReviewRepository
from app.services.errors import ServiceError

REVIEW_WINDOW_DAYS = 30
DAILY_REVIEW_LIMIT = 10
MIN_LOW_RATING_COMMENT = 15
MAX_COMMENT = 500
PRIOR_WEIGHT = 5          # C
DEFAULT_PRIOR = 4.0       # Hiç yorum yokken platform ortalaması yerine kullanılır (m)

_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|tr|io|xyz|ly)\b)", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(\+?90[\s-]?)?0?\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
_REPEAT = re.compile(r"(.)\1{5,}")  # aynı karakter 6+ kez: "çoooook kötüüüüü" değil, "!!!!!!!" / "aaaaaa"


def _utc(dt):
    """SQLite saat dilimi bilgisini kaybeder; o zaman değer UTC kabul edilir."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Kurallar --------------------------------------------------------------------------------

def review_problem(user, item):
    """Bu kullanıcı bu kalemi değerlendirebilir mi? Engel varsa nedenini (metin) döndürür."""
    order = item.order
    if not user.is_customer or order.customer_id != user.id:
        return "Yalnızca bu siparişi veren müşteri değerlendirme yapabilir."
    if order.status != OrderStatus.DELIVERED:
        return "Değerlendirme sipariş teslim edildikten sonra yapılabilir."
    if item.review is not None:
        return "Bu ürünü zaten değerlendirdiniz."
    delivered_at = _utc(order.updated_at)  # teslim son durumdur; sonrasında sipariş değişmez
    if delivered_at and datetime.now(timezone.utc) - delivered_at > timedelta(days=REVIEW_WINDOW_DAYS):
        return f"Değerlendirme süresi doldu (teslimden sonra {REVIEW_WINDOW_DAYS} gün)."
    return None


def content_problem(comment, rating):
    """Yorum metni kurallara uyuyor mu? Uymuyorsa nedeni."""
    text = (comment or "").strip()
    if rating <= 2 and len(text) < MIN_LOW_RATING_COMMENT:
        return (f"1-2 yıldız verirken nedenini en az {MIN_LOW_RATING_COMMENT} karakterle yazın; "
                "üretici sorunu ancak böyle düzeltebilir.")
    if len(text) > MAX_COMMENT:
        return f"Yorum en fazla {MAX_COMMENT} karakter olabilir."
    # E-posta önce: "satici@ornek.com" bir alan adı da içerir, kullanıcı doğru nedeni görsün
    if _EMAIL.search(text) or _PHONE.search(text):
        return "Yorumda telefon veya e-posta paylaşmayın (kişisel veri)."
    if _URL.search(text):
        return "Yorumda bağlantı (internet adresi) paylaşılamaz."
    if _REPEAT.search(text):
        return "Yorumda aynı karakteri art arda bu kadar çok tekrarlamayın."
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) >= 20 and all(ch.isupper() for ch in letters):
        return "Lütfen yorumun tamamını büyük harfle yazmayın."
    return None


# --- İşlemler --------------------------------------------------------------------------------

def create_review(user, item, rating, comment=None):
    problem = review_problem(user, item)
    if problem:
        raise ServiceError(problem)
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise ServiceError("Puan 1 ile 5 arasında olmalı.", field="rating")
    problem = content_problem(comment, rating)
    if problem:
        raise ServiceError(problem, field="comment")
    since = datetime.now(timezone.utc) - timedelta(days=1)
    if ReviewRepository.count_by_customer_since(user.id, since) >= DAILY_REVIEW_LIMIT:
        raise ServiceError(f"Bir günde en fazla {DAILY_REVIEW_LIMIT} değerlendirme yapabilirsiniz.")

    review = Review(order_item=item, customer=user, producer_id=item.producer_id, rating=rating,
                    comment=(comment or "").strip() or None, is_visible=True)
    ReviewRepository.add(review)
    try:
        ReviewRepository.commit()
        refresh_reputations()  # ilişkili kayıtlar: üreticilerin itibar önbelleği
    except Exception:
        ReviewRepository.rollback()
        raise
    return review


def set_visibility(review, visible):
    """Yönetici moderasyonu. Gizli yorum itibara katılmaz; itibar yeniden hesaplanır."""
    review.is_visible = bool(visible)
    ReviewRepository.commit()
    refresh_reputations()
    return review


# --- İtibar ----------------------------------------------------------------------------------

def compute_reputation(reviews, prior_mean=DEFAULT_PRIOR, prior_weight=PRIOR_WEIGHT):
    """Saf fonksiyon (veri tabanına dokunmaz, testi kolay). Dönüş: (itibar, müşteri sayısı).

    reviews: (müşteri_id, puan) çiftleri. Her müşteri tek oy: önce müşteri başına ortalama alınır.
    """
    per_customer = defaultdict(list)
    for customer_id, rating in reviews:
        per_customer[customer_id].append(rating)
    votes = [sum(r) / len(r) for r in per_customer.values()]
    if not votes:
        return 0.0, 0
    score = (prior_weight * prior_mean + sum(votes)) / (prior_weight + len(votes))
    return round(score, 2), len(votes)


def update_reputation(producer):
    """Üreticinin itibarını görünür yorumlardan yeniden hesaplar ve profile kaydeder.

    review_count = görünür YORUM sayısı (ekranda "12 değerlendirme"); itibar ise müşteri başına tek oyla.
    """
    reviews = ReviewRepository.visible_for_producer(producer.id)
    prior = ReviewRepository.platform_average()
    score, _ = compute_reputation([(r.customer_id, r.rating) for r in reviews],
                                  prior_mean=float(prior) if prior is not None else DEFAULT_PRIOR)
    producer.reputation_score = score
    producer.review_count = len(reviews)
    ReviewRepository.commit()
    return score


def refresh_reputations():
    """Yorumu olan TÜM üreticilerin itibarını yeniden hesaplar.

    Neden hepsi? Bayes ortalamasındaki platform ortalaması her yeni yorumla değişir; yalnızca yorum
    alan üreticiyi güncellemek diğerlerinin puanını eskimiş bırakırdı. Veri küçük, hesap ucuz.
    Ayrıca: flask recompute-reputation
    """
    return {p.id: update_reputation(p) for p in ReviewRepository.producers_with_reviews()}


# --- Sorgular --------------------------------------------------------------------------------

def product_summary(product):
    return ReviewRepository.product_summary(product.id)


def latest_for_product(product, limit=10):
    return ReviewRepository.latest_for_product(product.id, limit)


def producer_reviews(profile):
    return ReviewRepository.list_for_producer(profile.id)


def all_reviews(only_hidden=False):
    return ReviewRepository.list_all(only_hidden=only_hidden)


def get_review(review_id):
    return ReviewRepository.get_by_id(review_id)
