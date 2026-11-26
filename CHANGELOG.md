# Değişiklik Günlüğü (CHANGELOG)

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) düzenine, sürüm numaraları
[Semantic Versioning](https://semver.org/lang/tr/) kuralına (MAJOR.MINOR.PATCH) uyar.
Her sürüm bir Git etiketiyle (`git tag -a vX.Y.Z`) işaretlenir.

## [Yayımlanmadı]
- Hafta 11: Değerlendirme ve itibar modülü (planlanan → `0.11.0`)

## [0.10.7] - 2026-11-27
### Düzeltildi
- Yapay zekânın gerekçeleri "Yeniden hesapla" sonrası görünmüyordu (kayıtlı öneride gerekçe alanı yoktu).
  `price_predictions.reasons` sütunu eklendi (migration `b81c4e2d9a57`)
- Testler: toplam 191

## [0.10.6] - 2026-11-27
### Düzeltildi
- Canlıda Gemini fiyat önerisi zaman aşımına uğruyordu (`gemini-3.8-flash` 30 sn içinde yanıt vermedi,
  tekrar deneme de aşıldı; kural tabanlı öneriye düşülüyordu). Varsayılan model `gemini-3.5-flash-lite`
  (en hızlı ücretsiz model), düşünme `minimal`, tek deneme ve 60 sn zaman aşımı
- AI günlüğünde her çağrının süresi (sn) görünüyor

## [0.10.5] - 2026-11-27
### Kaldırıldı
- Yapay zekâ fotoğraf incelemesi (0.10.4'te eklenmişti) isteğe göre kaldırıldı: sayfa, 📷 düğmesi,
  `app/ai/photo_review.py`, testleri. Fotoğrafların veri tabanında saklanması kalıyor
- Testler: toplam 190

## [0.10.4] - 2026-11-27
### Eklendi
- **Fotoğraf incelemesi:** yapay zekâ (Gemini veya Claude) ürün fotoğrafına bakar; fotoğrafın ürünü
  gösterip göstermediğini, görünen tazeliği, fotoğraf kalitesini (1-5) ve ilan için önerileri verir.
  `/uretici/urunler/<id>/fotograf-incelemesi` (Ürünlerim → 📷). Çıktı `validate_photo_output` ile doğrulanır;
  kural tabanlı yedek yok, sorun olursa nedeni gösterilir. Günde ürün başına en fazla 5 inceleme
- Testler: fotoğraf incelemesi ve fotoğraf saklama (toplam 204)

### Değişti
- Ürün fotoğrafları diskte değil **veri tabanında** (`product_images` tablosu, migration `a7d3e9f1b204`).
  Render'ın ücretsiz planında disk geçici olduğu için yüklenen fotoğraflar her güncellemede ve uyandırmada
  siliniyordu. Fotoğraf `/urun-resmi/<id>` adresinden sunulur
- Eski sürümde diske yüklenmiş ama silinmiş fotoğraflar için kırık resim yerine yer tutucu gösterilir

### Düzeltildi
- `migrations_flask/env.py`: yerel SQLite'ta `flask db upgrade` son migration'ları kaydetmiyordu
  (PRAGMA komutu SQLAlchemy 2'de işlem başlatıyor, Alembic commit etmiyordu). PostgreSQL etkilenmiyordu

## [0.10.3] - 2026-11-26
### Düzeltildi
- Canlıda öneri sayfası 503 veriyordu: gunicorn isteği 30 sn'de kesiyordu, yapay zekâ çağrısı
  (30 sn zaman aşımı + bir yeniden deneme) bundan uzun sürebiliyordu. `gunicorn.conf.py`: `timeout = 120`
- Gemini yanıtı kural tabanlıya düşüyordu: Gemini 3'ün "düşünme" adımı `maxOutputTokens`'tan düşüyor,
  cevap yarıda kalabiliyordu. `thinkingConfig.thinkingLevel = "low"`, `maxOutputTokens` 8192;
  model bu ayarı reddederse (400) ayarsız tekrar denenir
- Yapay zekâ çıktısı kullanılmadığında nedeni Render günlüğüne (Logs) de yazılıyor

## [0.10.2] - 2026-11-26
### Eklendi
- Ücretsiz yapay zekâ seçeneği: Google Gemini (ücretsiz katman). `.env` içine yalnızca
  `GEMINI_API_KEY` yazılırsa öneriler Gemini ile üretilir; ek paket gerekmez (Hafta 9'daki HTTP katmanı kullanılır)
- Ayarlar: `GEMINI_API_KEY`, `AI_PROVIDER` (gemini / anthropic); `AI_MODEL` sağlayıcıya göre varsayılan alır
- Gemini şemayı reddederse (HTTP 400) şemasız bir kez daha denenir; hız sınırı (429) ve kesik/boş yanıt kural tabanlı öneriye düşer
- Testler: Gemini yolu için 7 test (gerçek API çağrılmaz)

### Değişti
- Öneri sayfasında hangi modelin kullanıldığı yazıyor (önceden sabit "Claude")
- Belgeler: Hafta 9'a örnek istek/yanıt bölümü (fiyat, hız sınırı, ödeme, Gemini); Hafta 10 belgesi iki sağlayıcıya göre güncellendi; test sayısı 189

## [0.10.1] - 2026-11-18
### Eklendi
- `flask remove-demo-listings`: demo üreticilerin ilanlarını Pazar'dan kaldırır (siparişi olan kapatılır);
  Render açılış komutunda çalışır. Demo hesaplar ve ürünler kalır
- Test: `test_remove_demo_listings` (toplam 182)
- Belge: gerçek hal fiyatı kaynağı araştırması (`docs/HAFTA9_API_ENTEGRASYONU.md`); AI kullanım günlüğü Hafta 9-10 notları

## [0.10.0] - 2026-11-18 — Hafta 10: Yapay zekâ bileşeni
### Eklendi
- Fiyat trendi ve satış zamanı önerisi: `/uretici/urunler/<id>/fiyat-onerisi` (Ürünlerim → 📈 düğmesi)
- `app/ai/trend.py`: fiyat serisi analizi (doğrusal regresyon, R², oynaklık, 7 günlük tahmin) ve kural tabanlı öneri
- `app/ai/llm_advisor.py`: istem tasarımı, Anthropic Claude çağrısı (JSON şemalı yapılandırılmış çıktı), çıktı doğrulama
- `app/services/ai_service.py`: hatalı/boş çıktıda kural tabanlı öneriye geçiş, günlük önbellek, günde 5 yenileme sınırı
- AI günlüğü: `instance/ai_gunlugu.jsonl` ve yönetici sayfası `/yonetici/ai-gunlugu`
- `price_predictions` tablosu artık dolduruluyor
- Ayarlar: `ANTHROPIC_API_KEY`, `AI_MODEL` (anahtar yoksa bileşen kapalı, uygulama çalışır)
- Paket: `anthropic` (resmi Python SDK'sı)
- Testler: `tests/test_ai.py` (45 test; toplam 181)
- Belge: `docs/HAFTA10_YAPAY_ZEKA.md`

## [0.9.0] - 2026-11-18 — Hafta 9: Harici API entegrasyonu
### Eklendi
- Ortak HTTP katmanı `app/integrations/http.py`: zaman aşımı, yeniden deneme, 429 `Retry-After`, 7 hata sınıfı
- Hal fiyatı istemcisi (gerçek + sahte), yanıt doğrulama; `flask fetch-prices --days N`
- Herkese açık `/hal-fiyatlari` sayfası; yönetici "Fiyatları güncelle" düğmesi (dakikada bir)
- Ödeme istemcisi (gerçek + test modu): HMAC imza, `Idempotency-Key`, test kartları
- Ödeme formu `/siparislerim/<id>/odeme` (Luhn ve son kullanma kontrolü; kart bilgisi saklanmaz)
- Ödenmiş siparişin iptalinde sağlayıcıdan iade; iade başarısızsa sipariş iptal edilmez
- Ayarlar: `USE_MOCK_APIS`, `PRICE_API_*`, `PAYMENT_API_*` (yalnızca ortam değişkeni)
- Testler: `tests/test_api_integration.py` (38 test)
- Belge: `docs/HAFTA9_API_ENTEGRASYONU.md`

### Değişti
- Sipariş artık durum düğmesiyle "ödendi" yapılamaz; yalnızca ödeme formuyla (sahte `_mock_payment` kaldırıldı)
- Başarısız ödemede sipariş "ödeme bekleniyor" durumunda kalır, tekrar denenebilir
- `render.yaml`: açılışta `flask fetch-prices --days 60`; `USE_MOCK_APIS`, `ANTHROPIC_API_KEY` değişkenleri
- Masaüstü sürümü açılışta örnek hal fiyatlarını yükler

## [0.8.3] - 2026-11-01
### Değişti
- Kapya biber fotoğrafı düzeltildi (yeşil biber yerine kırmızı kapya biber)

## [0.8.2] - 2026-11-01
### Değişti
- Demo ürün görselleri çizimden gerçek fotoğraflara çevrildi (`.jpg`, 4:3). Kaynak notu: `app/static/img/demo/KAYNAK.md`
- `flask seed-demo` eski demo görselini (`.png`) yenisiyle değiştirir; üreticinin kendi yüklediği görsele dokunmaz

## [0.8.1] - 2026-11-01
### Eklendi
- Demo ürünlerine örnek görseller (`app/static/img/demo/`, projede çizilmiş illüstrasyonlar). Canlıda görselsiz eklenmiş demo ürünlerine `flask seed-demo` görseli sonradan ekler.
- Test: `test_demo_products_have_sample_images` (toplam 98 test)

## [0.8.0] - 2026-11-01 — Vize ara sürümü
Kullanıcı + veri tabanı + çekirdek modüller (ürün, ilan, sepet, sipariş) uçtan uca çalışır.

### Eklendi
- Uçtan uca entegrasyon testleri, duman (smoke) testi ve regresyon testleri (`tests/test_integration.py`, 10 test; toplam 97)
- Yönetici paneli özeti: kullanıcı (role göre), ürün, açık ilan, sipariş (duruma göre), ciro
- Yönetici sipariş takibi: `/yonetici/siparisler` (durum filtresi) ve `/yonetici/siparisler/<id>`
- Sürüm numarası (`app/__init__.py` → `__version__`) ve sayfanın alt bilgisinde gösterimi
- `flask seed-demo` demo yöneticisi de ekler (`yonetici@example.com`, parola `DEMO_PASSWORD`)
- Belgeler: `docs/HAFTA8_ARA_SURUM.md`, `DEMO_SENARYOSU.md`, `AI_KULLANIM_GUNLUGU.md`, `ILERLEME_RAPORU.md`, `SOZLU_HAFTA8.md`

### Düzeltildi
- SQLite'ta yabancı anahtar denetimi kapalıydı; artık her bağlantıda `PRAGMA foreign_keys = ON` (yerel ve canlı aynı davranır)
- Bir müşterinin sepetindeki ilana sahip ürün silinince oluşan 500 hatası (`IntegrityError`)
- İlanı olan ürünün biriminin (kg → adet) değiştirilebilmesi
- Yöneticinin sipariş durumunu değiştirdikten sonra genel panele atılması

### Değişti
- `/yonetici/panel` rotası `main_routes.py`'den `admin_routes.py`'ye taşındı (adres aynı)
- Migration sırasında SQLite yabancı anahtar denetimi geçici kapatılır (`migrations_flask/env.py`)

## [0.7.0] - 2026-11-01 — Hafta 7 (etiketsiz)
İlan, sepet, sipariş yaşam döngüsü (durum makinesi), mock ödeme, Render canlı yayın.

## [0.6.0] - Hafta 6 (etiketsiz)
Üretici profili, ürün CRUD, görsel yükleme, hızlı stok güncelleme, yönetici kategori yönetimi.

## [0.5.0] - Hafta 5 (etiketsiz)
Kayıt/giriş, rol tabanlı yetkilendirme, CSRF, hatalı giriş sınırı.

## [0.3.0 - 0.4.0] - Hafta 3-4 (etiketsiz)
Proje iskeleti, katmanlı mimari, ER modeli; Node.js + SQLite veri tabanı alıştırması.

> 0.8.0 öncesi sürümler geriye dönük yazılmıştır; o haftalarda Git etiketi atılmamıştı
> ("ara sürümü etiketlememek" hatası). 0.8.0 ilk etiketli sürümdür.
