# Değişiklik Günlüğü (CHANGELOG)

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) düzenine, sürüm numaraları
[Semantic Versioning](https://semver.org/lang/tr/) kuralına (MAJOR.MINOR.PATCH) uyar.
Her sürüm bir Git etiketiyle (`git tag -a vX.Y.Z`) işaretlenir.

## [Yayımlanmadı]
- Hafta 9: Hal fiyatı API entegrasyonu ve gerçek ödeme altyapısı (planlanan → `0.9.0`)

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
