# Yapay Zekâ Kullanım Günlüğü

**Öğrenci:** Fidan · **Proje:** Tarladan Sofraya · **Kullanılan araç:** Claude (Anthropic)
**Kural:** Yapay zekânın önerdiği her kodu okudum, çalıştırdım, testlerle denedim ve açıklayabiliyorum.
Anlamadığım kodu projeye almadım; anlamadığım yeri yapay zekâya tekrar sordum.

> Bu günlük her hafta güncellenir. "Benim katkım / doğrulamam" sütunu benim kendi notumdur;
> sözlüde hangi kodu nasıl kontrol ettiğimi buradan anlatırım.

| Hafta | Amaç (neden kullandım) | Yapay zekâ ne yaptı | Benim katkım / nasıl doğruladım |
|---|---|---|---|
| 3 | Proje iskeleti ve mimari | Flask katmanlı klasör yapısını, modelleri ve `docs/MIMARI.md` şemasını önerdi | ER modelini kendi proje fikrime (üretici, ürün, ilan, sipariş, hal fiyatı) göre seçtim; `python run.py` ile açıldığını kontrol ettim |
| 4 | Veri tabanı tasarımı | Node.js + SQLite migration, seed ve CRUD örneklerini yazdı; DDL/DML, indeks, transaction kavramlarını anlattı | `npm run hepsi` ile çalıştırdım; yabancı anahtar ve CHECK kısıtlarını hatalı veri ekleyerek denedim; N-N ara tabloyu (`urun_kategori`) kendim açıkladım |
| 5 | Kimlik doğrulama ve güvenlik | Kayıt/giriş, parola özeti (hash), rol dekoratörü, CSRF, hatalı giriş sınırı | Testleri çalıştırdım (55 test); 5 hatalı girişte hesabın kilitlendiğini elle denedim; `docs/GUVENLIK_NOTU.md` |
| 6 | Üretici ve ürün modülü | Ürün CRUD, görsel yükleme doğrulaması, sahiplik kontrolü, hızlı stok formu | Başka üreticinin ürün numarasını adres çubuğuna yazıp 404 aldığımı gördüm; stok için CHECK kısıtını açıkladım |
| 7 | İlan, sepet, sipariş + canlı yayın | Sipariş durum makinesi, checkout transaction'ı, koşullu UPDATE ile stok düşme, Render dosyası | Canlıya kendim çıkardım (`git push`, Render Blueprint). İlk kurulum bölge farkı yüzünden çöktü; hata mesajını okuyup düzeltmeyi uyguladım |
| 8 | **Entegrasyon hatalarını ayıklama ve refaktör** | Modüller arası yolları deneyen testler yazdırdım; 4 hata buldu ve düzeltti; yönetici panelini tamamladı; sürüm numarası ve CHANGELOG | Her düzeltmeyi aşağıda açıkladım. Regresyon testlerinin eski kodda **başarısız**, yeni kodda **başarılı** olduğunu gördüm (98 test geçiyor) |
| 9 | Harici API entegrasyonu (fiyat + ödeme) | Ödeme sağlayıcılarının API belgelerindeki kavramları (idempotency anahtarı, HMAC imza, sandbox test kartları, `Retry-After`) açıkladı; ortak HTTP katmanını, istemcileri, ödeme akışını ve 38 testi yazdı | Ödeme akışını canlı sitede test kartıyla kendim denedim. Ödemeden sonra sipariş benim üretici hesabımda görünmeyince inceledim: siparişin ilanın sahibine (demo üreticiye) gittiğini öğrendim. Demo ilanların kaldırılmasına karar verdim ve kendi 6 ilanımı fidan hesabıyla Pazar'a ekledim. Kart sahibi alanına gerçek bilgi yazmadım. Değişiklikleri önce ayrı dala (`hafta-9-10`) gönderttim, sonra `main`'e birleştirip `v0.10.0` etiketini attırdım. Gerçek fiyat kaynağı için İBB'nin hal fiyatı servisini araştırttık; servis yanıt vermediği için sahte servis kullanılıyor (`docs/HAFTA9_API_ENTEGRASYONU.md`, Bölüm 7) |
| 10 | **Yapay zekâ bileşeni** (çekirdek işlev) | Trend analizini (regresyon), istemi, JSON şemasını, çıktı doğrulama kurallarını, yedek (kural tabanlı) akışı ve 45 testi yazdı | Bileşenin kodunu yapay zekâ yazdı; ben kapsamını ve çalışma kurallarını (anahtar yoksa kural tabanlı öneri, kişisel veri gönderilmemesi) onayladım. 45 test bilgisayarımda çalıştırıldı ve geçti (toplam 182). API anahtarımı yapay zekâyla paylaşmadım; anahtar yalnızca Render panelinde tutulur. Gerçek Claude çağrısı anahtar girildikten sonra `/yonetici/ai-gunlugu` sayfasında kayıt olarak görünür |

---

## Hafta 8 ayrıntısı: yapay zekâdan gelen değişiklikler ve açıklamam

### 1. `app/__init__.py` → `_sqlite_foreign_keys_on`
- **Sorun:** SQLite yabancı anahtarı varsayılan olarak denetlemiyor. Yerelde hatalı silme geçiyor, canlıda (PostgreSQL) patlıyordu.
- **Değişiklik:** Her yeni veri tabanı bağlantısında `PRAGMA foreign_keys = ON` çalışır.
- **Neden doğru:** Hafta 4'te Node.js tarafında (`src/db.js`) aynı satır vardı. `test_regression_sqlite_foreign_keys_enforced` PRAGMA'nın 1 döndüğünü kontrol ediyor.
- **Dikkat ettiğim:** PostgreSQL bağlantısında `isinstance(..., sqlite3.Connection)` yanlış döner, fonksiyon hiçbir şey yapmaz.

### 2. `producer_service.delete_product` → önce sepet kalemleri
- **Sorun:** Sepette olan ürün silinince 500 hatası.
- **Değişiklik:** Ürün silinmeden önce ilanlarına bağlı sepet kalemleri siliniyor.
- **Neden doğru:** Yabancı anahtar kuralı: bağımlı kayıt (sepet kalemi) ana kayıttan (ilan) önce silinmeli. `listing_service.delete_listing` içinde aynı kural zaten vardı.

### 3. `producer_service.update_product` → ilanı varsa birim değişmez
- **Sorun:** kg → adet değişince ilan ve eski siparişler yanlış birimle görünüyordu.
- **Değişiklik:** `if unit != product.unit and product.listings:` durumunda hata mesajı.

### 4. Yönetici sipariş sayfaları + panel
- **Sorun:** Yönetici sipariş iptal edebiliyordu ama siparişleri görebileceği sayfa yoktu.
- **Değişiklik:** `admin_routes.py` içinde 3 rota; `StatsRepository.get_summary_stats()` içinde `COUNT ... GROUP BY` sorguları. Şablonlar `admin_view` değişkeniyle yeniden kullanıldı.
- **Yapay zekânın kendi hatası:** İlk denemede `/yonetici/panel` adresi iki dosyada tanımlı kaldı ve sonsuz yönlendirme oluştu. Duman testi bunu yakaladı, eski rota silindi. **Ders:** Yapay zekâ kodu da hata yapabilir; testler olmadan fark etmezdim.

### 5. `tests/test_integration.py` (10 test)
- Testleri yapay zekâ yazdı. Senaryoyu (üretici → müşteri → yönetici) ben belirledim; demo senaryosuyla birebir aynı.

---

## Hafta 9-10: Uygulamanın içindeki yapay zekâ (Claude API)

Hafta 10'dan itibaren yapay zekâ yalnızca geliştirme aracı değil, **uygulamanın bir parçası**:
"Fiyat Trendi ve Satış Zamanı Önerisi" bileşeni Claude API'sini çağırır.
- **İstem:** `app/ai/llm_advisor.py` → `SYSTEM_PROMPT` ve `build_prompt()` (sürüm: `PROMPT_VERSION`)
- **Çıktı doğrulama:** `validate_output()`; geçmeyen çıktı kullanılmaz, kural tabanlı öneri gösterilir
- **Her çağrının kaydı:** `instance/ai_gunlugu.jsonl` (istem, ham çıktı, sorunlar, hangi önerinin kullanıldığı); yönetici sayfası `/yonetici/ai-gunlugu`
- **Gizlilik:** Modele yalnızca ürün türü ve hal fiyatı gider; kişisel veri gitmez
- Ayrıntı: `docs/HAFTA10_YAPAY_ZEKA.md`

---

## Yapay zekâyı kullanmadığım / kendim yaptığım işler
- Proje konusu ve modüllerin seçimi
- Canlı yayın hesabı (Render), `git push`, Git etiketi (`git tag v0.8.0`)
- Demo senaryosunu sunmak ve sözlü sınavda kodu anlatmak
- Her haftanın sonunda testleri kendi bilgisayarımda çalıştırmak

## Sorumlu kullanım notları
- Gerçek kişisel veri yapay zekâya verilmedi; tüm örnek veriler uydurma (`example.com`).
- Gizli anahtarlar (`SECRET_KEY`, `DEMO_PASSWORD`, `ANTHROPIC_API_KEY`, ödeme anahtarları) yapay zekâyla paylaşılmadı, koda yazılmadı.
