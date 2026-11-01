# Hafta 8 — Vize Ara Sürümü (v0.8.0): Entegrasyon, Hata Giderme, Etiketleme

**Proje:** Çiftçi Doğrudan Satış ve Fiyat Takip Platformu ("Tarladan Sofraya")
**Sürüm:** `v0.8.0` · **Canlı adres:** https://tarladan-sofraya.onrender.com
**İlgili belgeler:** [Demo senaryosu](DEMO_SENARYOSU.md) · [AI kullanım günlüğü](AI_KULLANIM_GUNLUGU.md) ·
[İlerleme raporu](ILERLEME_RAPORU.md) · [Sözlü hazırlık](SOZLU_HAFTA8.md) · [Değişiklik günlüğü](../CHANGELOG.md)

---

## 1. Bu haftanın özeti

| Yapılacak iş (ödev) | Ne yaptım | Nerede |
|---|---|---|
| Modüllerin uçtan uca entegrasyonu | Kayıt → ürün → ilan → sepet → sipariş → ödeme → kargo → teslim zinciri tek testte ve tarayıcıda çalıştırıldı; yönetici paneli tüm modüllerin verisini tek ekranda gösteriyor | `tests/test_integration.py`, `app/routes/admin_routes.py` |
| Bilinen hataların giderilmesi | 4 entegrasyon hatası bulundu ve düzeltildi (aşağıda) | `app/__init__.py`, `producer_service.py`, `order_routes.py` |
| Ara sürüm etiketleme | Sürüm numarası `0.8.0`, sayfanın alt bilgisinde görünür; `CHANGELOG.md`; Git etiketi komutları | `app/__init__.py`, `CHANGELOG.md`, bölüm 6 |
| Kısa demo senaryosu | 7-8 dakikalık adım adım senaryo | `docs/DEMO_SENARYOSU.md` |

Testler: **87 → 97 test**, hepsi geçiyor (`python -m pytest`).

---

## 2. Modül haritası: hangi modül hangi veriyi nereden alıyor?

```
            ┌─────────────────────────── Kullanıcı modülü (Hafta 5) ──────────────────────────┐
            │ auth_routes → auth_service → UserRepository → users, roles                       │
            │ Giriş yapan kullanıcı (current_user) ve rolü TÜM modüllere buradan gelir          │
            └───────────────┬─────────────────────────────┬───────────────────────────┬────────┘
                            │ rol = producer              │ rol = customer            │ rol = admin
                            ▼                             ▼                           ▼
┌──────── Üretici & Ürün (Hafta 6) ────────┐  ┌──────── Sepet (Hafta 7) ─────┐  ┌──── Yönetici (H6 + H8) ────┐
│ producer_profiles  ← users.id            │  │ carts       ← users.id       │  │ categories (H6)            │
│ products ← producer_profiles.id,         │  │ cart_items  ← listings.id    │  │ panel: users, products,    │
│            categories.id (Yönetici)      │  └──────────────┬───────────────┘  │ listings, orders sayıları  │
└──────────────────┬───────────────────────┘                 │ ödeme (checkout)  │ (StatsRepository, H8)      │
                   ▼                                         ▼                   └────────────────────────────┘
┌──────── İlan (Hafta 7) ──────────────────┐  ┌──────── Sipariş (Hafta 7) ─────────────────────┐
│ listings ← products.id                   │─▶│ orders      ← users.id (müşteri)                │
│ Vitrin: aktif + stoklu + süresi dolmamış │  │ order_items ← listings.id, producer_profiles.id │
│ + ürünü satışa açık ilanlar              │  │ payments    ← orders.id (şimdilik mock ödeme)   │
└──────────────────────────────────────────┘  └─────────────────────────────────────────────────┘
```

| Modül | Okuduğu veri (nereden) | Yazdığı veri |
|---|---|---|
| Kullanıcı (H5) | `users`, `roles` | `users`; üretici kaydında `producer_profiles` |
| Üretici/Ürün (H6) | `current_user.producer_profile`, `categories` (yönetici ekler), `listings` (açık ilan miktarı, H7 kuralı) | `products`, `producer_profiles` |
| İlan (H7) | `products` (yalnızca kendi ve satışa açık ürünler, depo stoğu) | `listings` |
| Sepet (H7) | `listings` (satışta mı, stok, en az miktar), `current_user` | `carts`, `cart_items` |
| Sipariş (H7) | `cart_items` → `listings` → `products.producer_id` | `orders`, `order_items` (fiyat kopyalanır), `payments`; `listings` ve `products` stoğunu düşer/geri ekler |
| Yönetici (H6+H8) | Tüm tablolardan sayım (`COUNT`, `SUM`) | `categories`; sipariş durumu |

**Önemli bağlantı noktaları (entegrasyonun kırılabileceği yerler):**
1. **Ürün ↔ İlan stoğu:** İlan miktarlarının toplamı depo stoğunu aşamaz; depo stoğu da açık ilanların altına inemez.
2. **Sepet ↔ İlan:** Sepet stok düşmez; ödeme anında her kalem yeniden kontrol edilir.
3. **Sipariş ↔ İlan + Ürün:** Sipariş tek işlemde (transaction) iki stoğu da düşer; iptal ikisini de geri ekler.
4. **Ürün silme ↔ Sepet:** Silinen ürünün ilanı birinin sepetindeyse önce sepet kalemi silinmeli (Hata 2).

---

## 3. Bulunan ve düzeltilen hatalar

Hepsi **entegrasyon hatası**: Her modül kendi testinde çalışıyordu, sorun iki modül birleşince çıktı.
Her hata için önce onu yakalayan bir **regresyon testi** yazıldı, test eski kodda başarısız oldu, düzeltmeden sonra geçti.

### Hata 1 — SQLite'ta yabancı anahtar (FOREIGN KEY) denetimi kapalıydı
- **Belirti:** Yerelde (SQLite) sahipsiz kayıt bırakan işlemler sessizce geçiyordu; aynı işlem canlıda (PostgreSQL) hata veriyordu. Yani "bende çalışıyor, sunucuda çalışmıyor".
- **Neden:** SQLite, yabancı anahtar kısıtlarını **varsayılan olarak denetlemez**. Her bağlantıda `PRAGMA foreign_keys = ON` gerekir. Hafta 4'teki Node.js kodunda (`src/db.js`) bu vardı, Flask tarafında unutulmuştu.
- **Düzeltme:** `app/__init__.py` → `_sqlite_foreign_keys_on()`: SQLAlchemy'nin `connect` olayına bağlanan fonksiyon, her yeni SQLite bağlantısında PRAGMA'yı açar. PostgreSQL bağlantısına dokunmaz.
- **Ek:** `migrations_flask/env.py`: migration sırasında denetim geçici kapatılır. Çünkü SQLite'ta `ALTER TABLE` (batch modu) tabloyu kopyalayıp eskisini siler; denetim açıkken bu adım takılabilir (Alembic belgelerinin önerisi).
- **Test:** `test_regression_sqlite_foreign_keys_enforced`

### Hata 2 — Sepette olan ürün silinince 500 hatası
- **Belirti:** Üretici, siparişe girmemiş ama bir müşterinin sepetinde duran ürününü silince sayfa **500 Internal Server Error** veriyordu (`IntegrityError: NOT NULL constraint failed: cart_items.listing_id`).
- **Neden:** Hafta 6'da ürün silme yazılırken sepet yoktu. Hafta 7'de sepet gelince ürün → ilan → sepet kalemi zinciri oluştu; ürün silinince ilan da (cascade) siliniyor, ama sepet kalemi ilansız kalıyordu.
- **Düzeltme:** `producer_service.delete_product()`: Önce ürünün ilanlarına ait sepet kalemleri silinir (`CartRepository.delete_items_for_listing`), sonra ürün. Kural: **ilişkili (bağımlı) kayıtlar önce silinir.** İlan silmede (`listing_service.delete_listing`) bu kural zaten vardı; ürün silmede eksikti.
- **Test:** `test_regression_delete_product_that_is_in_a_cart`

### Hata 3 — İlanı olan ürünün birimi değiştirilebiliyordu
- **Belirti:** "Bal" ürünü kg ile ilana çıkmışken birimi "adet" yapılınca "2,5 kg" ilan "2,5 adet"e dönüşüyor; eski siparişler de yanlış birimle görünüyordu (adet için kesirli miktar zaten yasak).
- **Düzeltme:** `producer_service.update_product()`: Ürünün en az bir ilanı varsa birim değişikliği reddedilir ve "yeni ürün ekleyin" mesajı gösterilir.
- **Test:** `test_regression_unit_cannot_change_when_product_has_listings`

### Hata 4 — Yönetici sipariş durumunu değiştirince siparişi kaybediyordu
- **Belirti:** Yetki tablosunda (`TRANSITIONS`) yönetici sipariş iptal edebiliyor ama yöneticinin sipariş görebileceği bir sayfa yoktu; işlemden sonra genel panele atılıyordu.
- **Düzeltme:** Yönetici için `/yonetici/siparisler` (liste + durum filtresi) ve `/yonetici/siparisler/<id>` (detay) eklendi; işlemden sonra aynı siparişe dönülür. Aynı `orders/list.html` ve `orders/detail.html` şablonları `admin_view` değişkeniyle yeniden kullanıldı (kod tekrarı yok).
- **Ek:** Yönetici paneli artık boş değil: kullanıcı (role göre), ürün, açık ilan, sipariş (duruma göre) sayıları ve ciro. Hepsi `StatsRepository.get_summary_stats()` içinde `COUNT`/`SUM` sorgularıyla gelir.
- **Canlıda yönetici:** Ücretsiz Render planında terminal olmadığı için `flask create-admin` canlıda çalışmıyordu. `flask seed-demo` artık `yonetici@example.com` demo yöneticisini de ekler (parolası `DEMO_PASSWORD`, koda yazılmaz). Test: `test_demo_data_is_synthetic_idempotent_and_usable`.
- **Not:** `/yonetici/panel` adresi önce `main_routes.py` içindeydi; `admin_routes.py`'ye taşındı. İkisi aynı adresi tanımlayınca sonsuz yönlendirme oluştu, entegrasyon testi bunu yakaladı ve eski rota kaldırıldı.
- **Test:** `test_regression_admin_status_change_returns_to_order`, `test_smoke_every_page_opens_for_every_role`

---

## 4. Entegrasyon testi yaklaşımı

| Test türü | Ne dener? | Örnek (bu projede) |
|---|---|---|
| **Birim testi** | Tek fonksiyon, tek kural | `test_slugify_turkish_characters` |
| **Modül testi** | Bir modülün rotası + servisi + veri tabanı | `test_shop.py`, `test_producer.py` |
| **Entegrasyon testi** | Birden çok modül birlikte, gerçek kullanıcı gibi | `test_end_to_end_happy_path` |
| **Duman (smoke) testi** | Her sayfa açılıyor mu? (derin kontrol yok, hızlı) | `test_smoke_every_page_opens_for_every_role` |
| **Regresyon testi** | Düzeltilen hata geri geldi mi? | `test_regression_*` |

Yaklaşımım (**büyük patlama değil, artımlı entegrasyon**): Her hafta yeni modül eklendiğinde eski testler de çalıştırıldı (Hafta 6'da 50, Hafta 7'de 87, Hafta 8'de 97 test). Bu hafta modüllerin **arasındaki** yolları deneyen testler eklendi.

`tests/test_integration.py` içindeki testler veri tabanına doğrudan kayıt eklemez; her şeyi **formlarla** yapar (kayıt formu, ürün formu, ilan formu, sepet, ödeme). Böylece form → rota → servis → repository → veri tabanı zincirinin tamamı denenir.

Çalıştırma:
```
python -m pytest                              # tüm testler (97)
python -m pytest -v tests/test_integration.py # yalnızca entegrasyon testleri (10)
```

---

## 5. Semantic Versioning (anlamsal sürümleme)

Biçim: **`MAJOR.MINOR.PATCH`** → örnek `0.8.0`

| Kısım | Ne zaman artar? | Bu projede |
|---|---|---|
| MAJOR | Geriye uyumsuz büyük değişiklik | `0` = henüz kararlı değil (geliştirme sürümü). Final teslimde `1.0.0` |
| MINOR | Geriye uyumlu yeni özellik/modül | Haftalık modüller: Hafta 8 → `0.8.0`, Hafta 9 (hal fiyatı API) → `0.9.0` |
| PATCH | Yalnızca hata düzeltmesi | Vizeden sonra küçük düzeltme gerekirse `0.8.1` |

- Sürüm numarası tek yerde tutulur: `app/__init__.py` → `__version__ = "0.8.0"`. Her sayfanın alt bilgisinde `v0.8.0` görünür; hoca canlı sitede hangi sürümü gördüğünü anlar.
- Git etiketi (`v0.8.0`) ile kodu aynı sürüm numarası taşır. Değişiklikler `CHANGELOG.md` dosyasında yazılıdır.
- `v` öneki Git etiketlerinde yaygın bir alışkanlıktır (`v0.8.0`); sürüm numarasının kendisi `0.8.0`'dır.

---

## 6. Git etiketi (tag) nasıl atılır? — VS Code terminalinde

> Terminal `satş` klasöründe açılıyorsa önce iç klasöre gir:
> `cd ciftci-platformu\ciftci-platformu`

```
git status                         # değişiklikleri gör
python -m pytest                   # ÖNCE testler geçmeli (97 passed)
git add .
git commit -m "Hafta 8: Entegrasyon, 4 hata düzeltmesi, entegrasyon testleri, v0.8.0"
git tag -a v0.8.0 -m "Vize ara sürümü: kullanıcı + ürün + ilan + sepet + sipariş uçtan uca"
git push                           # commit'leri gönder
git push origin v0.8.0             # etiketi gönder (git push etiketleri KENDİLİĞİNDEN göndermez!)
```

Kontrol:
```
git tag                            # v0.8.0 listede olmalı
git show v0.8.0 --stat             # etiketin hangi commit'e bağlı olduğu
```
GitHub'da: depo sayfası → **Tags** (veya **Releases → Draft a new release → v0.8.0** seçip `CHANGELOG.md`'deki 0.8.0 bölümünü yapıştır).

**Hafif (lightweight) etiket ile açıklamalı (annotated, `-a`) etiket farkı:** Açıklamalı etiket kimin, ne zaman ve hangi mesajla attığını saklar; sürümler için önerilen budur.

**Yanlış commit'e etiket attıysam?** (henüz push etmediysen) `git tag -d v0.8.0` ile sil, doğru commit'te tekrar at.

Canlı site: `git push` sonrası Render otomatik yeniden kurar; birkaç dakika sonra sitenin alt bilgisinde `v0.8.0` görünür.
