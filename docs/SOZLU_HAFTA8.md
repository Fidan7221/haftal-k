# Vize Sözlü Sınavı Hazırlığı (Hafta 8)

Cevapları ezberleme; kendi cümlelerinle söyle. Her cevapta **bir dosya adı** göstermek hocaya kodu bildiğini kanıtlar.

---

## Soru 1 — Şu ana kadarki mimarini özetle.

"Proje Python Flask ile yazılmış, **katmanlı mimari** kullanıyor. Dört katman var:

1. **Sunum:** `app/routes/` (hangi adres hangi sayfa), `app/forms/` (doğrulama), `app/templates/` (HTML).
2. **İş:** `app/services/`, iş kuralları burada: stok negatif olamaz, siparişi olan ürün silinmez, sipariş durum geçişleri.
3. **Veri erişimi:** `app/repositories/`, sorgular burada. Rota doğrudan SQL yazmaz.
4. **Model / veri tabanı:** `app/models/`, SQLAlchemy ile 14 tablo. Yerelde SQLite, canlıda PostgreSQL.

Her modül bir **blueprint**: auth, producer, admin, listing, cart, order, main. Uygulama `create_app()` fabrikasıyla kuruluyor; bu sayede testlerde bellekte geçici veri tabanı kullanabiliyorum. Tablolar Flask-Migrate migration'larıyla oluşuyor. Canlı yayın Render'da, `render.yaml` dosyasıyla. Şu anki sürüm **v0.8.0**, Git'te etiketli."

**Göster:** `docs/MIMARI.md`, `app/__init__.py`

---

## Soru 2 — Hangi modül hangi veriyi nereden alıyor?

"Her şeyin başlangıcı **kullanıcı modülü**. Giriş yapan kullanıcı (`current_user`) ve rolü diğer bütün modüllere oradan gelir.

- **Ürün modülü** üreticinin profilini `users`'tan, kategoriyi yöneticinin eklediği `categories` tablosundan alır.
- **İlan modülü** ürünü ve depo stoğunu `products`'tan alır. İlanların toplamı depo stoğunu aşamaz.
- **Sepet** ilanı `listings`'ten alır: satışta mı, stok yetiyor mu, en az miktar ne?
- **Sipariş** sepetten oluşur: `cart_items` → `listings` → `products.producer_id`. Sepet üreticiye göre bölünür. Fiyat sipariş kalemine **kopyalanır**, stok hem ilandan hem depodan düşer.
- **Yönetici paneli** tüm tablolardan `COUNT` ve `SUM` ile özet alır."

**Göster:** `docs/HAFTA8_ARA_SURUM.md` bölüm 2 (tablo ve şema)

---

## Soru 3 — En çok zorlandığın entegrasyon neydi, nasıl çözdün?

**Örnek cevap (sepetteki ürünü silme, Hata 2 + Hata 1):**

"En çok **ürün modülü ile sepet modülünün birleşmesinde** zorlandım. Ürün silmeyi Hafta 6'da yazmıştım; o zaman sepet yoktu. Hafta 7'de sepet gelince, bir müşterinin sepetinde ilanı olan ürünü silince sayfa **500 hatası** verdi.

Daha garibi, bazı durumlarda yerelde hata görünmüyordu ama canlıda çıkıyordu. Nedenini araştırınca öğrendim: **SQLite yabancı anahtarları varsayılan olarak denetlemiyor**, PostgreSQL denetliyor. Hafta 4'te Node.js tarafında `PRAGMA foreign_keys = ON` yazmıştım ama Flask tarafında unutmuştum.

Çözüm iki adım oldu:
1. `app/__init__.py` içinde her SQLite bağlantısında PRAGMA'yı açtım. Artık yerel ve canlı aynı davranıyor.
2. `producer_service.delete_product` içinde ürünü silmeden önce o ürünün ilanlarına bağlı sepet kalemlerini sildim. **Bağımlı kayıt önce silinir.**

Önce hatayı yeniden üreten bir **regresyon testi** yazdım. Test kırmızıydı, düzeltince yeşil oldu."

**Göster:** `tests/test_integration.py` → `test_regression_delete_product_that_is_in_a_cart`

*(Alternatif: Ürün stoğu ile ilan stoğunun senkron tutulması (Hafta 7). İlan toplamı depoyu aşamaz, depo da ilanların altına inemez. `_check_listing_reserve`)*

---

## Soru 4 — Yapay zekâdan aldığın bir kod parçasını satır satır açıkla.

### Seçenek A: Yabancı anahtar düzeltmesi (`app/__init__.py`)

```python
@event.listens_for(Engine, "connect")                       # 1
def _sqlite_foreign_keys_on(dbapi_connection, connection_record):   # 2
    import sqlite3                                          # 3
    if isinstance(dbapi_connection, sqlite3.Connection):    # 4
        cursor = dbapi_connection.cursor()                  # 5
        cursor.execute("PRAGMA foreign_keys = ON")          # 6
        cursor.close()                                      # 7
```
1. `@event.listens_for(Engine, "connect")`: SQLAlchemy'ye "veri tabanına **her yeni bağlantı** açıldığında bu fonksiyonu çağır" der. Olay dinleyici (event listener).
2. Fonksiyon iki parametre alır: `dbapi_connection` ham bağlantı nesnesi, `connection_record` bağlantı havuzundaki kaydıdır (kullanmıyoruz ama imzada olmak zorunda).
3. Python'un SQLite modülünü içe aktarırız.
4. Bağlantı SQLite mi? PostgreSQL ise bu koşul yanlış olur ve hiçbir şey yapılmaz. PostgreSQL zaten yabancı anahtarları denetler.
5. Komut çalıştırmak için imleç (cursor) açılır.
6. `PRAGMA foreign_keys = ON`: SQLite'a özel ayar komutu. Bu bağlantıda yabancı anahtar kısıtlarını **denetlemeye başla** der. Ayar bağlantı başına geçerli olduğu için her bağlantıda tekrar yazılır.
7. İmleç kapatılır (kaynak boşa harcanmasın).

### Seçenek B: Koşullu UPDATE ile stok düşme (`listing_repository.decrease_stock`, Hafta 7)

```python
result = db.session.execute(
    update(Listing)                                                    # 1
    .where(Listing.id == listing_id, Listing.stock_quantity >= quantity)  # 2
    .values(stock_quantity=Listing.stock_quantity - quantity)         # 3
)
return result.rowcount                                                 # 4
```
1. `listings` tablosunda güncelleme yapılacak.
2. Yalnızca bu ilan **ve** stok istenen miktara yetiyorsa.
3. Stoğu, veri tabanının kendi içinde (`stok = stok - miktar`) azalt.
4. Kaç satır güncellendi? 1 ise başarılı, 0 ise stok yetmedi.

SQL karşılığı: `UPDATE listings SET stock_quantity = stock_quantity - :q WHERE id = :id AND stock_quantity >= :q`
**Neden böyle?** Kontrol ve düşme **tek cümlede**. Aynı anda iki müşteri son ürünü almaya çalışsa bile stok eksiye düşmez (yarış durumu / race condition).

---

## Soru 5 — Bir sonraki aşamanın planı nedir?

"**Hafta 9'da sürüm 0.9.0** olacak, harici API entegrasyonu:
- **Hal fiyatı API'si:** Ürünün kategorisine göre güncel hal fiyatını gösterip üreticinin fiyatıyla karşılaştıracağım. Projenin 'fiyat takip' ayağı bu. `market_prices` tablosu ve `config.py`'deki `PRICE_API_URL` hazır.
- **Ödeme API'si (test modu):** Şu an sahte (mock) ödeme var. `USE_MOCK_APIS` ayarı ile gerçek API'ye geçilecek.

Sonra Hafta 10-11'de fiyat geçmişi grafiği ve yapay zekâ ile fiyat tahmini (`price_predictions` tablosu), Hafta 12-13'te yorumlar ve raporlar. Final teslimde **1.0.0** kararlı sürüm."

**Göster:** `docs/ILERLEME_RAPORU.md` bölüm 6

---

## Ek sorular (gelebilir)

**S: Neden 0.8.0? Neden 1.0.0 değil?**
"Semantic Versioning: MAJOR.MINOR.PATCH. MAJOR 0 'henüz kararlı değil, geliştiriliyor' demek. Her haftalık modül yeni özellik, yani MINOR artar: Hafta 8 → 0.8.0. Nitekim v0.8.0'dan sonra demo ürünlerine örnek görsel ekledim; yeni modül olmadığı için yalnızca PATCH arttı: 0.8.1."

**S: Git etiketi ne işe yarar?**
"Belirli bir commit'e kalıcı isim verir. Hoca 'vizede gösterdiğin kod' dediğinde `git checkout v0.8.0` ile tam o hâline dönebilirim. `-a` ile açıklamalı etiket attım; kimin, ne zaman attığını saklar. `git push` etiketleri göndermez, `git push origin v0.8.0` ayrıca gerekir."

**S: Birim testi ile entegrasyon testi farkı?**
"Birim testi tek fonksiyonu dener, örneğin `slugify`. Entegrasyon testi birden çok modülü birlikte dener. Benim `test_end_to_end_happy_path` testim üretici kaydından teslimata kadar her şeyi formlarla yapıyor."

**S: Regresyon nedir?**
"Yeni bir değişikliğin, önceden çalışan bir şeyi bozması. Örneğin Hafta 7'de sepet ekleyince Hafta 6'daki ürün silme bozuldu. Bunu önlemek için her değişiklikten sonra **tüm** testleri çalıştırıyorum. Düzelttiğim her hata için de bir regresyon testi yazdım, hata geri gelirse test kırmızı olur."

**S: Duman (smoke) testi nedir?**
"Derine inmeden 'her sayfa açılıyor mu?' diye bakan hızlı test. Benim testim her rol için tüm sayfaları açıp 500 hatası olmadığını kontrol ediyor. Yönetici panelini taşırken oluşan sonsuz yönlendirmeyi bu test yakaladı."

**S: Entegrasyonu neden son ana bırakmadın?**
"Her hafta yeni modülü eklerken eski testleri de çalıştırdım: Hafta 6'da 50, Hafta 7'de 87, şimdi 98 test. Yani **artımlı entegrasyon** yaptım. Hepsini sonda birleştirseydim (büyük patlama / big bang) hatanın hangi modülden geldiğini bulmak çok zor olurdu."

**S: Yapay zekâyı nasıl kullandın?**
"Hata ayıklama ve refaktör için kullandım, `docs/AI_KULLANIM_GUNLUGU.md` dosyasına haftalık yazdım. Her değişikliği testle doğruladım. Yapay zekânın kendi hatası da oldu: yönetici paneli rotasını iki yerde bıraktı, sonsuz yönlendirme oluştu. Testim yakaladı. Anlamadığım kodu projeye almadım."

---

## Teorik kavramlar (tek cümlelik)
| Kavram | Tanım | Projemde |
|---|---|---|
| **Entegrasyon** | Ayrı geliştirilen modüllerin birlikte çalışır hâle getirilmesi | Ürün ↔ ilan stoğu, sepet → sipariş, ürün silme ↔ sepet |
| **Entegrasyon testi** | Modüllerin birlikte doğru çalıştığını deneyen test | `tests/test_integration.py` |
| **Sürümleme (SemVer)** | MAJOR.MINOR.PATCH ile değişikliğin büyüklüğünü anlatan numara | `__version__ = "0.8.0"`, `CHANGELOG.md` |
| **Git tag** | Bir commit'e verilen kalıcı sürüm adı | `git tag -a v0.8.0` |
| **Regresyon** | Yeni değişikliğin eski özelliği bozması | Sepet eklendi → ürün silme bozuldu |
| **Regresyon testi** | Düzeltilen hatanın geri gelmediğini kontrol eden test | `test_regression_*` |
| **Duman testi** | Hızlı "sistem ayakta mı?" kontrolü | `test_smoke_every_page_opens_for_every_role` |

## Sık yapılan hatalar (ben ne yaptım?)
| Hata | Benim önlemim |
|---|---|
| Entegrasyonu son ana bırakmak | Her hafta tüm testler; bu hafta uçtan uca test |
| Ara sürümü etiketlememek | `v0.8.0` etiketi + `CHANGELOG.md` + sayfa altında sürüm |
| Açıklanamayan AI kodu taşımak | AI günlüğü; her değişikliğin açıklaması; regresyon testleri |
