# Çekirdek Modül B: İlan, Sepet ve Sipariş (Hafta 7 teslim çıktısı — ilgili kod ve kısa açıklama)

Canlı yayın adımları ayrı belgede: [CANLI_YAYIN.md](CANLI_YAYIN.md)

## 1. Ne yapar?

| Kim | Ne yapabilir | Adres |
|---|---|---|
| Herkes | Satıştaki ilanları görür, arar, kategoriye göre süzer | `/ilanlar`, `/ilanlar/<id>` |
| Üretici | Kendi ürününe ilan açar (fiyat, miktar, en az sipariş, bitiş tarihi) | `/uretici/ilanlar/yeni` |
| Üretici | İlanlarını listeler, düzenler, kapatır/açar, siler | `/uretici/ilanlar` |
| Müşteri | Sepete ekler, miktar günceller, çıkarır | `/sepet`, `/sepet/ekle/<id>` |
| Müşteri | Sepetten sipariş oluşturur (adres + not) | `/sepet/odeme` |
| Müşteri | Siparişlerini görür, öder (deneme ödemesi), iptal eder, teslim aldığını onaylar | `/siparislerim` |
| Üretici | Gelen siparişleri duruma göre süzer, kargoya verir, iptal eder | `/uretici/siparisler` |

## 2. Dosyalar (katmanlara göre)

| Katman | Dosya | İçerik |
|---|---|---|
| Model | `app/models/listing.py`, `cart.py`, `order.py`, `payment.py` | `Listing`, `Cart`, `CartItem`, `Order`, `OrderItem`, `OrderStatus`, `Payment` |
| Veri erişimi | `app/repositories/listing_repository.py`, `cart_repository.py`, `order_repository.py` | Sahiplikli sorgular, **koşullu stok UPDATE'i** |
| İş mantığı | `app/services/listing_service.py`, `cart_service.py`, `order_service.py` | Kurallar, checkout işlemi, **durum makinesi** |
| Sunum | `app/routes/listing_routes.py`, `cart_routes.py`, `order_routes.py`, `app/forms/shop_forms.py` | Rotalar ve formlar |
| Şablon | `app/templates/listings/`, `cart/`, `orders/`, `producer/listings.html`, `producer/listing_form.html` | Bootstrap 5 arayüz |
| Test | `tests/test_shop.py` (32 test) | Toplam 87 test geçiyor |
| Canlı yayın | `render.yaml`, `config.py` (`database_url`, `ProductionConfig`), `migrations_flask/`, `scripts/demo_data.py` | |

## 3. Veri modeli ve ilişkiler

```
producer_profiles 1──N products 1──N listings
                                       │1
users 1──1 carts 1──N cart_items N──1──┤
                                       │1
users 1──N orders 1──N order_items N───┘   order_items N──1 producer_profiles
              │1
              └──1 payments
```

- **Ürün ≠ İlan:** Ürün depodaki maldır (`products.stock_quantity`). İlan, o malın satışa ayrılan kısmı ve fiyatıdır.
  Bir ürünün birden çok ilanı olabilir (ör. "1. kalite 30 TL", "salçalık 15 TL").
- **Sepet kalemi ve sipariş kalemi ilana bağlıdır**, ürüne değil: fiyat ilanda durur.
- **Sepet ile Sipariş ayrı tablolardır.** Sepet geçicidir ve değişir; sipariş kalıcı bir kayıttır, değişmez.
- **Fiyat dondurma:** `order_items.unit_price` sipariş anındaki fiyatın kopyasıdır. İlan fiyatı sonra değişse de eski sipariş tutarı değişmez.
- **N-N ilişkiler:** Sepet–İlan arasında `cart_items`, Sipariş–İlan arasında `order_items` ara tablodur (miktar gibi ek bilgi taşırlar).
- **Kısıtlar (veri tabanı seviyesinde):** `CHECK(price >= 0)`, `CHECK(stock_quantity >= 0)`, `CHECK(quantity > 0)`,
  `UNIQUE(cart_id, listing_id)` (aynı ilan sepette iki satır olamaz), `UNIQUE(carts.user_id)` (her müşterinin tek sepeti).

> Bu hafta şema değişikliği gerekmedi: tablolar Hafta 3-4'te tasarlanmıştı. Bu hafta akışlar (iş mantığı) yazıldı.

## 4. İş kuralları ve doğrulama

| Kural | Nerede | Neden |
|---|---|---|
| Üretici yalnızca KENDİ ürününe ilan açar, kendi ilanını değiştirir | `ListingRepository.get_for_producer` → yoksa **404** | Adresteki id'yi değiştirerek başkasının ilanı değiştirilemesin (IDOR) |
| Arşivlenmiş ürüne ilan açılmaz | `create_listing` | Satışa kapalı mal satılmasın |
| Fiyat > 0, miktar > 0, en az sipariş ≤ miktar, bitiş tarihi geçmişte olamaz | Form + `listing_service._validate` | Anlamsız ilan oluşmasın |
| **Açık ilanların toplamı depo stoğunu aşamaz** | `_validate` → `open_stock_for_product` | Depoda olmayan mal satılmasın |
| Depo stoğu, ilanlara ayrılan miktarın altına indirilemez | `producer_service._check_listing_reserve` | Aynı kuralın ters yönü (Hafta 6 ile tutarlılık) |
| adet/kasa/demet satışta miktar tam sayı | `check_unit_quantity` | 2,5 kasa satılamaz |
| Sepete yalnızca satıştaki ilan eklenir; miktar ≥ en az sipariş ve ≤ stok | `cart_service._check` | |
| Aynı ilan tekrar eklenirse miktar toplanır | `add_to_cart` + `UNIQUE(cart_id, listing_id)` | Sepette mükerrer satır olmasın |
| Sepet/sipariş yalnızca müşteri rolüne açık | `@role_required(RoleName.CUSTOMER)` → **403** | |
| Müşteri yalnızca KENDİ sepet kalemini ve siparişini görür | `get_item_for_user`, `get_for_customer` → **404** | |
| Sepete eklemek stok düşmez; **siparişte yeniden kontrol** | `order_service.checkout` | Sepette beklerken stok bitebilir |
| Stok düşme koşullu: `WHERE stock_quantity >= :q` | `ListingRepository.decrease_stock` | Aynı anda iki kişi son ürünü alamasın |
| Siparişe girmiş ilan silinmez, kapatılır | `delete_listing` | Geçmiş siparişler ilana bağlı (ilişkili kayıt yönetimi) |
| İlan silinirken sepetlerdeki kalemleri de silinir | `CartRepository.delete_items_for_listing` | Yabancı anahtar hatası / öksüz kayıt olmasın |
| İptalde stok ilana ve depoya geri eklenir; ödenmişse ödeme "iade" olur | `_restore_stock` | |

**Neden hem formda hem serviste doğrulama?** Form kullanıcıya anında hata gösterir ama atlanabilir
(biri doğrudan POST isteği gönderebilir). Servis her yoldan (form, test, ileride API) gelen isteği kontrol eder.
Veri tabanı `CHECK` kısıtı da son savunma hattıdır.

## 5. Sipariş durumları (durum makinesi)

```
 pending ──(müşteri öder)──> paid ──(üretici kargolar)──> shipped ──(teslim)──> delivered
 Ödeme bekleniyor            Ödendi                         Kargoda                Teslim edildi
    │                          │
    └─────(iptal)──────────────┴────> cancelled (İptal edildi)
```

Kodun kalbi `app/services/order_service.py` içindeki tablo:

```python
# {mevcut durum: {yeni durum: {bu geçişi yapabilecek roller}}}
TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.PAID: {CUSTOMER},
        OrderStatus.CANCELLED: {CUSTOMER, PRODUCER, ADMIN},
    },
    OrderStatus.PAID: {
        OrderStatus.SHIPPED: {PRODUCER, ADMIN},
        OrderStatus.CANCELLED: {CUSTOMER, PRODUCER, ADMIN},
    },
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED: {CUSTOMER, PRODUCER, ADMIN}},
    OrderStatus.DELIVERED: {},   # son durum
    OrderStatus.CANCELLED: {},   # son durum
}
```

- `change_status()` önce tabloya bakar: geçiş tabloda yoksa (ör. `pending → delivered`) **"durumuna geçemez"** hatası.
- Sonra rol: müşteri "Kargoya verdim" diyemez → **"yetkiniz yok"**.
- Sayfadaki düğmeler de aynı tablodan üretilir (`allowed_actions`), yani ekranda yalnızca yapılabilecek işlemler görünür.
- Kargoya verilmiş sipariş iptal edilemez (tabloda `shipped → cancelled` yok).

## 6. Sepetten siparişe geçiş (checkout) — tek işlem (transaction)

```python
# app/services/order_service.py  (kısaltılmış)
def checkout(user, shipping_address, note=None):
    cart = CartRepository.get_by_user(user.id)
    # 1) Her kalemi YENİDEN doğrula (ilan hâlâ satışta mı, stok yetiyor mu?)
    # 2) Sepeti üreticiye göre böl -> her üretici için ayrı Order
    try:
        for producer_id, items in groups.items():
            order = Order(customer=user, status=OrderStatus.PENDING, ...)
            for item in items:
                # 4) Koşullu UPDATE: 0 satır dönerse stok başkası tarafından alınmış
                if ListingRepository.decrease_stock(listing.id, item.quantity) == 0: raise ServiceError(...)
                # 3) Fiyatı dondur
                order.items.append(OrderItem(listing=listing, quantity=item.quantity, unit_price=listing.price))
        # 5) Sepeti boşalt
        OrderRepository.commit()      # hepsi birlikte kalıcı olur
    except Exception:
        OrderRepository.rollback()    # ya hepsi ya hiçbiri
        raise
```

Koşullu stok düşmenin SQL karşılığı:

```sql
UPDATE listings SET stock_quantity = stock_quantity - 4
 WHERE id = 7 AND stock_quantity >= 4;   -- etkilenen satır 0 ise stok yetmedi
```

## 7. Diğer modüllerle entegrasyon

| Önceki modül | Bu hafta nasıl kullanıldı |
|---|---|
| Hafta 4 veri modeli | Tablolar hazırdı (listings, carts, cart_items, orders, order_items, payments); yeni tablo açılmadı |
| Hafta 5 kimlik doğrulama | `@role_required` ile müşteri/üretici sayfaları ayrıldı, tüm POST formlarında CSRF |
| Hafta 6 ürün modülü | İlan yalnızca üreticinin aktif ürününe açılır; stok güncellemesi ilan miktarının altına inemez; ürün arşivlenince ilanları vitrinden düşer |
| Katmanlı mimari | Route → Service → Repository; servis `db.session` kullanmaz |
| Hafta 9 (sonra) | `_mock_payment` yerine gerçek ödeme API'si bağlanacak; `Payment` tablosu hazır |
| Hafta 11 (sonra) | `delivered` siparişin kalemlerine yorum (`reviews.order_item_id`) yapılabilecek |

## 8. Sık yapılan hatalar → bu projede ne yapıldı

| Hata | Önlem |
|---|---|
| Doğrulamayı atlamak | Form + servis + veri tabanı CHECK (üç katman) |
| Erişim/sahiplik kontrolünü unutmak | Rol için 403, başkasının kaydı için 404; testler: `test_producer_cannot_edit_others_listing`, `test_cannot_touch_others_cart_item`, `test_other_customer_cannot_see_order` |
| İlişkili kayıtları yönetmemek | Siparişli ilan silinmez/kapatılır, ilan silinirken sepet kalemleri silinir, iptalde stok geri eklenir, sipariş başlığı + kalemleri + stok tek transaction |
| Canlı ortam değişkenlerini eksik bırakmak | `SECRET_KEY` yoksa uygulama canlıda açılmaz; `render.yaml` tüm değişkenleri listeler; `.env.example` şablonu |

## 9. Sözlü sınav soruları ve kısa cevaplar

**1) Sipariş durumlarını nasıl tasarladın?**
Beş durum var: ödeme bekleniyor, ödendi, kargoda, teslim edildi, iptal. Bunları bir **durum makinesi** olarak
`order_service.py` içindeki `TRANSITIONS` tablosunda tanımladım: her durumdan hangi duruma geçilebileceği ve bu
geçişi kimin (müşteri, üretici, yönetici) yapabileceği yazıyor. Tabloda olmayan geçiş reddediliyor, ör. ödenmemiş
sipariş "teslim edildi" yapılamaz; teslim edilmiş veya iptal edilmiş sipariş son durumdur. İptalde stok geri eklenir,
ödenmişse ödeme "iade" olur. Ekrandaki düğmeler de aynı tablodan üretilir.

**2) Sepetten siparişe geçişi nasıl kurdun?**
`checkout()` fonksiyonu tek bir **transaction**: önce her sepet kalemini yeniden kontrol ediyorum (sepette beklerken
stok bitmiş olabilir). Sonra sepeti üreticiye göre bölüp her üretici için ayrı sipariş açıyorum, kaleme o anki fiyatı
kopyalıyorum (fiyat dondurma), stoğu `WHERE stock_quantity >= miktar` koşullu UPDATE ile düşüyorum ve sepeti
boşaltıyorum. Herhangi bir adım hata verirse `rollback` ile hiçbiri kalıcı olmuyor: ya hepsi ya hiçbiri.

**3) Bu modülün verisini nasıl modelledin?**
Ürün ile ilanı ayırdım: ürün depodaki mal, ilan satışa çıkan kısım + fiyat. Sepet (`carts`, her müşteriye bir tane)
ve sepet kalemleri (`cart_items`) geçici; sipariş (`orders`) ve sipariş kalemleri (`order_items`) kalıcı. Kalemler
ilana bağlı; sipariş kaleminde `unit_price` ve `producer_id` ayrıca saklanıyor. Sepet–ilan ve sipariş–ilan N-N
ilişkileri ara tablolarla kuruldu. CHECK ve UNIQUE kısıtları veri tabanında da kuralı koruyor.

**4) Canlı sunucu dağıtımını nasıl yaptın ve ortam değişkenlerini nasıl yönettin?**
Kodu GitHub'a gönderip Render'a bağladım. `render.yaml` dosyası bir web servisi ve bir PostgreSQL veri tabanı
kuruyor. Kurulumda `pip install`, açılışta `flask db upgrade` (migration ile tablolar), `flask seed-db` ve `gunicorn`
çalışıyor. Gizli bilgiler koda yazılmıyor: `SECRET_KEY`'i Render rastgele üretiyor, `DATABASE_URL` veri tabanından
otomatik geliyor, `DEMO_PASSWORD`'u ben paneldan giriyorum. Yerelde aynı değişkenler `.env` dosyasında,
`.env` git'e gönderilmiyor. `FLASK_ENV=production` ile hata ayıklama kapanıyor, çerezler yalnızca HTTPS ile gidiyor;
`SECRET_KEY` unutulursa uygulama bilerek açılmıyor.

**5) Bu modülü diğer modüllerle nasıl entegre ettin?**
Hafta 4'teki tabloları kullandım, yeni tablo gerekmedi. Hafta 5'teki `@role_required` ile sepeti yalnızca müşteriye,
ilan yönetimini yalnızca üreticiye açtım. Hafta 6'daki ürünle bağ kurdum: ilan yalnızca kendi aktif ürününe açılıyor,
depo stoğu ilanlara ayrılan miktarın altına indirilemiyor, sipariş olunca hem ilan hem ürün stoğu düşüyor. Aynı
katmanlı yapıyı (rota → servis → repository) sürdürdüm. Ödeme şimdilik sahte; Hafta 9'da `Payment` tablosuna gerçek
API bağlanacak.

## 10. Teorik kavramlar (kısa)

- **Veri modeli:** Varlıklar (ilan, sepet, sipariş), alanları ve aralarındaki ilişkiler (1-1, 1-N, N-N) ile kısıtlar.
- **İş kuralı / doğrulama:** "Stok eksiye düşmez", "kargodaki sipariş iptal edilemez" gibi alan kuralları. Doğrulama bu kuralların her girişte kontrol edilmesidir.
- **Modülerlik:** Her modül kendi dosyalarında (ilan, sepet, sipariş servisleri ayrı); modüller birbirini yalnızca servis fonksiyonlarıyla çağırır. Biri değişince diğerleri bozulmaz.
- **Deployment (canlıya alma):** Uygulamayı herkesin erişebileceği bir sunucuya kurmak: bağımlılıkların kurulması, ortam değişkenleri, veri tabanı, üretim web sunucusu (gunicorn) ve HTTPS adres.
