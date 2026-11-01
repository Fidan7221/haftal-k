# Kısa İlerleme Raporu — Vize (Hafta 8, v0.8.0)

**Proje:** Çiftçi Doğrudan Satış ve Fiyat Takip Platformu ("Tarladan Sofraya")
**Öğrenci:** Fidan · **Tarih:** 01.11.2026 · **Canlı:** https://tarladan-sofraya.onrender.com

## 1. Nerede duruyoruz?
Kullanıcı + veri tabanı + çekirdek modüller uçtan uca çalışıyor: Üretici ürün ekler ve ilan açar, müşteri sepete ekleyip sipariş verir ve öder (deneme ödemesi), üretici kargolar, müşteri teslim alır, yönetici tüm süreci panelden izler. Sürüm Git'te `v0.8.0` olarak etiketli.

## 2. Tamamlanan haftalar
| Hafta | Konu | Durum |
|---|---|---|
| 3 | Kurulum, mimari, ER modeli | ✅ |
| 4 | Veri tabanı tasarımı, CRUD (Node.js + SQLite alıştırması) | ✅ |
| 5 | Kullanıcı yönetimi, kimlik doğrulama, güvenlik | ✅ |
| 6 | Üretici ve ürün modülü | ✅ |
| 7 | İlan, sepet, sipariş + canlı yayın | ✅ |
| 8 | Entegrasyon, hata giderme, ara sürüm | ✅ |

## 3. Sayılarla
- **14 tablo** (11 tanesi şu an kullanılıyor; hal fiyatı, tahmin ve yorum tabloları sonraki haftalar için hazır), 1 Flask migration (`migrations_flask/`)
- **7 modül** (blueprint): main, auth, producer, admin, listing, cart, order
- **98 otomatik test**, hepsi geçiyor (Hafta 7 sonunda 87)
- **4 entegrasyon hatası** bulundu ve düzeltildi (`docs/HAFTA8_ARA_SURUM.md` bölüm 3)

## 4. Bu hafta yapılanlar
1. Uçtan uca entegrasyon testleri, duman testi ve regresyon testleri yazıldı.
2. Düzeltilen hatalar: SQLite yabancı anahtar denetimi, sepette olan ürünü silerken 500 hatası, ilanlı ürünün birim değişikliği, yönetici sipariş takibi.
3. Yönetici paneli tamamlandı (istatistikler + tüm siparişler).
4. Sürüm numarası (sayfa altında `v0.8.0`), `CHANGELOG.md`, Git etiketi.
5. Demo senaryosu ve AI kullanım günlüğü.

## 5. Riskler ve bilinen eksikler
| Risk / eksik | Etkisi | Plan |
|---|---|---|
| Ödeme sahte (mock) | Gerçek para akışı yok | Hafta 9: ödeme API'si (test modu) |
| Hal fiyatı modülü yok | Projenin "fiyat takip" ayağı eksik | Hafta 9: hal fiyatı API'si |
| Ücretsiz Render veri tabanı 30 günde siliniyor | Canlı veri kaybolabilir | Final öncesi yeniden kurulum veya Neon gibi ücretsiz kalıcı veri tabanı |
| Hatalı giriş sınırı bellekte tutuluyor | Sunucu yeniden başlarsa sayaç sıfırlanır | Kabul edilebilir; ileride veri tabanına taşınabilir |
| Üretici onayı / kullanıcı yönetimi yok | Yönetici üreticiyi doğrulayamıyor | Hafta 11-12 |

## 6. Sonraki aşamanın planı
- **Hafta 9 (v0.9.0):** Harici API entegrasyonu: hal fiyatları (ürün kategorisine göre karşılaştırma), ödeme API'si test modu. `config.py`'de `PRICE_API_URL` ve `USE_MOCK_APIS` hazır.
- **Hafta 10-11:** Fiyat geçmişi grafiği ve yapay zekâ ile fiyat tahmini (`price_predictions` tablosu hazır).
- **Hafta 12-13:** Değerlendirme (yorum) modülü, raporlar, test kapsamının artırılması.
- **Final (v1.0.0):** Kararlı sürüm, son belgeler, sunum.
