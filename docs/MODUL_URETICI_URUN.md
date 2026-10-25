# Çekirdek Modül A: Üretici ve Ürün Kaydı (Hafta 6 teslim çıktısı — ilgili kod ve kısa açıklama)

## 1. Ne yapar?

| Kim | Ne yapabilir | Adres |
|---|---|---|
| Üretici | Profilini düzenler (çiftlik adı, bölge, açıklama, vergi no) | `/uretici/profil` |
| Üretici | Ürünlerini listeler, arar, kategoriye göre süzer | `/uretici/urunler` |
| Üretici | Ürün ekler / düzenler (görselli) | `/uretici/urunler/yeni`, `/uretici/urunler/<id>/duzenle` |
| Üretici | Ürün siler (siparişi olan ürün silinmez, arşivlenir) | `/uretici/urunler/<id>/sil` (yalnızca POST) |
| Üretici | Ürün listesinden hızlı stok günceller | `/uretici/urunler/<id>/stok` (yalnızca POST) |
| Üretici | Panel özeti (toplam ürün, satıştaki ürün, düşük stok, son eklenenler) | `/uretici/panel` |
| Yönetici | Kategori ağacını yönetir (ana ve alt kategoriler) | `/yonetici/kategoriler` |

## 2. Dosyalar (katmanlara göre)

| Katman | Dosya | İçerik |
|---|---|---|
| Model | `app/models/producer.py`, `app/models/product.py` | `ProducerProfile`, `Category` (kendine bağlı), `Product`, `Unit` |
| Veri erişimi | `app/repositories/product_repository.py` | `get_for_producer`, `paginate_for_producer`, `has_orders`, `CategoryRepository` |
| İş mantığı | `app/services/producer_service.py`, `app/services/category_service.py` | Doğrulama, görsel kaydı, silme/arşivleme |
| Yardımcı | `app/utils/uploads.py` | Görsel imza kontrolü, rastgele dosya adı, güvenli silme |
| Sunum | `app/routes/producer_routes.py`, `app/routes/admin_routes.py`, `app/forms/producer_forms.py` | Rotalar ve formlar |
| Şablon | `app/templates/producer/products.html`, `product_form.html`, `profile.html` | Bootstrap 5 arayüz |
| Test | `tests/test_producer.py` (24), `tests/test_categories.py` (9) | |

## 3. Veri modeli ve ilişkiler

```
users 1──1 producer_profiles 1──N products N──1 categories (parent_id → categories)
```

- **Ürün–üretici ilişkisi:** `products.producer_id → producer_profiles.id` (1-N). Ürün doğrudan `users`'a değil profile bağlıdır,
  çünkü yalnızca üreticilerin ürünü olur.
- **Ürün–kategori:** `products.category_id → categories.id`. Üst kategori seçilince (Sebze) alt kategorilerin (Domates, Biber)
  ürünleri de listelenir.
- **Ürün ≠ İlan:** Ürün üreticinin elindeki maldır (toplam stok). Satışa çıkarılan kısım Hafta 7'deki `listings`'tir.

## 4. İş kuralları ve neden kondukları

| Kural | Nerede | Neden |
|---|---|---|
| Kategori gerçekten var olmalı | `_validate_product` | Formu atlayan bir istek olmayan kategori gönderebilir; ayrıca yabancı anahtar da engeller |
| Birim yalnızca kg, adet, kasa, demet, litre | `_validate_product`, `Unit.ALL` | Fiyat karşılaştırması ve raporlar birime göre yapılır |
| Stok negatif olamaz | Form (`NumberRange(min=0)`) + `_validate_product` + `update_stock` | Olmayan mal satışa çıkarılamasın |
| Üretici yalnızca KENDİ ürününü görür/düzenler | `ProductRepository.get_for_producer(id, producer_id)` → yoksa **404** | Adresteki numarayı değiştirerek başkasının ürününe erişilmesin (IDOR) |
| Siparişi olan ürün silinmez, arşivlenir (`is_active=False`) | `delete_product` | Geçmiş siparişler ürüne bağlıdır; silinirse sipariş geçmişi bozulur |
| Silme yalnızca POST + CSRF | rota | Bir bağlantıya tıklatarak (GET) ürün sildirilemesin |
| Görsel: uzantı + **dosya imzası** + en fazla 5 MB | `uploads.is_real_image` | Adı `.png` yapılmış bir program dosyası kabul edilmesin |
| Dosya adı kullanıcıdan alınmaz, `uuid` ile üretilir | `uploads.save_product_image` | `../../app.py` gibi yol saldırıları ve ad çakışmaları önlensin |
| Kayıt başarısız olursa yüklenen görsel silinir | `create_product` | Diskte sahipsiz dosya kalmasın |
| Alt kategorisi veya ürünü olan kategori silinmez | `delete_category` | Ürünler kategorisiz kalmasın |

## 5. Kodun kalbi (açıklamalı)

```python
# app/services/producer_service.py
def delete_product(product):
    """Siparişi olan ürünü arşivler, olmayanı tamamen siler."""
    if ProductRepository.has_orders(product.id):
        product.is_active = False          # satıştan kalkar ama geçmiş siparişler bozulmaz
        ProductRepository.commit()
        return "archived"
    image_path = product.image_path
    ProductRepository.delete(product)      # ilanlar ve tahminler (sonraki haftalar) cascade ile birlikte silinir
    ProductRepository.commit()
    delete_product_image(image_path, _upload_root())   # önce veri tabanı, SONRA dosya
    return "deleted"
```

Dosya, veri tabanı işlemi başarıyla bittikten **sonra** silinir: commit başarısız olsaydı ürün duracak ama görseli gitmiş olacaktı.

## 6. Diğer modüllerle entegrasyon

- **Hafta 5 (kimlik):** Üretici kaydında profil otomatik açılır; tüm üretici rotaları `@role_required(PRODUCER)`.
- **Hafta 7 (ilan, planlanan):** İlan formunda yalnızca üreticinin **aktif** ürünleri listelenecek; aktif ilanların toplam miktarı ürün stoğunu aşamayacak. O hafta `update_stock`'a "stok, aktif ilanlara ayrılan miktarın altına inemez" kuralı eklenecek.
- **Hafta 9-10 (planlanan):** Ürünün kategorisi hal fiyatı karşılaştırması ve yapay zekâ tahmini için kullanılacak.

## 7. Ödev maddeleri → projedeki karşılığı

| İstenen | Dosya | Not |
|---|---|---|
| Üretici modeli (user_id, çiftlik adı, şehir, açıklama, doğrulama) | `app/models/producer.py` → `ProducerProfile` | `user_id` UNIQUE (1-1), `farm_name`, `region` ("İl / İlçe"), `description`, `is_verified`; şehir ayrıca `users.city` |
| Ürün modeli (producer_id FK, kategori, başlık, açıklama, stok, birim, görsel, aktiflik) | `app/models/product.py` → `Product` | `name`, `stock_quantity`, `unit`, `image_path`, `is_active`, `is_organic` |
| Kategori modeli ve ürünlerle ilişkisi | `app/models/product.py` → `Category` | 1-N ürün, kendine bağlı alt kategori |
| Ürün formu, stok ≥ 0, zorunlu alanlar, görsel uzantısı ve boyutu | `app/forms/producer_forms.py` → `ProductForm`, `StockForm` | `FileAllowed(jpg, jpeg, png, webp)`, `FileSize(5 MB)`, `InputRequired`, `NumberRange(min=0)` |
| CRUD | `app/services/producer_service.py` + `app/repositories/product_repository.py` | `create_product`, `list_products`, `update_product`, `delete_product` |
| Sahiplik / yetki kontrolü | `ProductRepository.get_for_producer(id, producer_id)`, rotada `_owned_product_or_404` | Başkasının ürünü → **404**; üretici olmayan → **403** |
| Stok güncelleme fonksiyonu | `producer_service.update_stock` + rota `/uretici/urunler/<id>/stok` | Negatif ve boş değer reddedilir; başkasının ürünü 404 |
| `@role_required` ile üretici rotaları | `app/routes/producer_routes.py` | panel, ürün listesi, yeni, düzenle, sil, stok |
| Görsel yükleme yardımcısı | `app/utils/uploads.py` | Dosya imzası kontrolü, rastgele (uuid) ad, `static/uploads/products/` |
| Şablonlar | `app/templates/producer/product_form.html` (`enctype="multipart/form-data"`), `products.html` | Stok durumu, hızlı stok formu, düzenle/sil |
| Testler | `tests/test_producer.py` (24), `tests/test_categories.py` (9) | |

### Bilinçli tasarım farkları (sözlüde sorulursa)

- **Sahiplik ihlalinde 403 değil 404:** 403 "bu ürün var ama senin değil" demek olurdu; saldırgan numaraları deneyerek hangi
  ürünlerin var olduğunu öğrenirdi. Sorgu baştan `id = ? AND producer_id = ?` olduğu için başkasının ürünü hiç bulunmaz.
  Rol ihlalinde ise (müşterinin üretici paneline girmesi) **403** döner. `test_cannot_edit_other_producers_product` ve `test_customer_cannot_manage_products` testleri bu ayrımı doğrular.
- **`secure_filename` yerine rastgele (uuid) ad:** `secure_filename` adı temizler ama aynı adlı iki dosya birbirinin üzerine
  yazılabilir ve Türkçe karakterleri siler ("çilek.png" → "cilek.png" ya da boş). Kullanıcının verdiği ad hiç kullanılmadığı
  için yol saldırısı (`../../app.py`) imkânsızdır. Uzantı küçük harfe çevrilip izin listesinden kontrol edilir.
- **Uzantı + dosya imzası:** Yalnızca uzantıya bakmak yetmez; adı `.png` yapılmış bir program dosyası kabul edilirdi. İlk baytlar
  (PNG: `\x89PNG`, JPEG: `\xff\xd8\xff`) kontrol edilir. WEBP de kabul edilir (telefon fotoğrafları için).
- **Türkçe adresler** (`/uretici/urunler` gibi): Arayüz Türkçe olduğu için adresler de Türkçe; işlev aynıdır.
- **Alan adları:** `stock_quantity` (ondalıklı: 12,5 kg olabilir), `image_path` (tam adres değil, dosyanın göreli yolu), `name`.

## 8. Hafta 6 sözlü sınav soruları ve cevapları

**1. Ürün–üretici ilişkisini nasıl kurdun?**
1-N ilişki: `products.producer_id → producer_profiles.id` yabancı anahtarı. Bir üreticinin çok ürünü olur, her ürünün tek
üreticisi vardır. Ürünü `users`'a değil üretici profiline bağladım, çünkü yalnızca üreticilerin ürünü olur. Kodda iki yönlü
ilişki var: `profile.products` ve `product.producer` (`back_populates`).

**2. Stok yönetimini nasıl yaptın?**
Ürünün toplam stoğu `stock_quantity` sütunundadır; ondalıklıdır, 2 hane tutar (12,5 kg). Kurallar:
- Stok negatif olamaz. Bu kural formda ve serviste uygulanır; veri tabanı CHECK kısıtı kılavuzdaki Hafta 4 alıştırmasıyla eklenir.
- Ürün listesindeki hızlı stok formu (`update_stock`) yalnızca stok alanını değiştirir; aynı kural orada da geçerlidir.

Hafta 7'de satışa çıkan kısım ilanla (`listings`) ayrılacak; stok, aktif ilanlara ayrılan miktarın altına inemeyecek. Sipariş verilince stok düşecek, iptalde geri eklenecek.

**3. Bu modülün verisini nasıl modelledin?**
Üç tablo kullandım:
- `producer_profiles`: çiftlik adı, bölge, açıklama, doğrulanmış mı ve itibar puanı.
- `categories`: kendine bağlı bir ağaç (Sebze → Domates); slug benzersizdir.
- `products`: ad, kategori, birim, stok, açıklama, organik mi, satışta mı ve görsel yolu.

Görselin kendisi veri tabanında değil diskte tutulur; tabloda yalnızca dosyanın yolu durur. Birim sabit bir listeden seçilir
(kg, adet, kasa, demet, litre), çünkü fiyat karşılaştırması birime göre yapılır.

**4. Bu modülde hangi iş kuralını neden koydun?**
En önemlisi şu: **siparişi olan ürün silinmez, arşivlenir.** Geçmiş siparişler ürüne bağlıdır; ürün silinseydi sipariş geçmişi
ve raporlar bozulurdu. Diğer kurallar:
- Üretici yalnızca kendi ürününü düzenleyebilir; başkasının ürününde 404 alır.
- Görsel, dosya imzasıyla doğrulanır.
- Dosya adı kullanıcıdan alınmaz; böylece yol saldırısı yapılamaz.
- Stok negatif olamaz.

**5. Bu modülü diğer modüllerle nasıl entegre ettin?**
- **Hafta 5 (kimlik doğrulama):** Üretici kayıt olunca profili otomatik açılır. Tüm rotalar `@role_required(PRODUCER)` ile korunur; giriş yapmayan kullanıcı giriş sayfasına yönlendirilir, müşteri 403 alır.
- **Hafta 7 (sonraki adım):** İlan formunda yalnızca üreticinin aktif ürünleri listelenecek; aktif ilanların toplamı ürün stoğunu aşamayacak.
- **Hafta 9-10:** Ürünün kategorisi hal fiyatı karşılaştırması ve yapay zekâ tahmini için kullanılacak.

Bu haftanın bağlantıları (rol koruması, sahiplik) `tests/test_producer.py` ile test ediliyor.

