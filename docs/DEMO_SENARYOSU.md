# Vize Demo Senaryosu (v0.8.0) — yaklaşık 7-8 dakika

**Amaç:** Kullanıcı + veri tabanı + çekirdek modüllerin (ürün, ilan, sepet, sipariş) uçtan uca çalıştığını göstermek.
**Nerede:** Canlı site https://tarladan-sofraya.onrender.com (yedek: yerelde `python run.py`)

> **Sunumdan 10 dakika önce** canlı siteyi bir kez aç. Ücretsiz Render planı boşta kalınca uyur;
> ilk açılış 30-60 saniye sürebilir. Sayfanın en altında **v0.8.1** yazdığını kontrol et (0.8.0 + örnek görseller düzeltmesi).

## Hazırlık

| Hesap | E-posta | Parola |
|---|---|---|
| Üretici 1 | `uretici1@example.com` | Render'a girdiğin `DEMO_PASSWORD` |
| Üretici 2 | `uretici2@example.com` | aynı |
| Müşteri | `musteri@example.com` | aynı |
| Yönetici | `yonetici@example.com` | aynı (v0.8.0 yayına girdikten sonra oluşur) |

- Hepsi **uydurma** hesaplar; `example.com` gerçek kimseye ait olamaz (KVKK).
- Tarayıcıda iki pencere aç: normal pencere (üretici) + **gizli pencere** (müşteri). Böylece çıkış/giriş yapmadan iki rolü yan yana gösterirsin.
- Yerelde gösterim gerekirse: `flask db upgrade` → `flask seed-db` → `.env` içine `DEMO_PASSWORD=...` → `flask seed-demo` → `python run.py`

---

## Adım 1 — Mimari (30 sn, slayt veya `docs/MIMARI.md`)
**Söyle:** "Proje Flask ile katmanlı yazıldı: rota → servis → repository → veri tabanı. Yerelde SQLite, canlıda PostgreSQL. Vize sürümü v0.8.0 Git'te etiketli; sonra demo görselleri için küçük bir düzeltme yaptım, o yüzden sitede v0.8.1 yazıyor. PATCH numarası arttı çünkü yeni modül yok."

## Adım 2 — Ziyaretçi vitrini (45 sn)
1. Ana sayfa → **İlanlar**. Arama kutusuna `domates` yaz; kategori filtresini göster.
2. Bir ilana tıkla → "Satın almak için giriş yapın" düğmesi.

**Söyle:** "Vitrinde yalnızca aktif, stoğu olan, süresi dolmamış ve ürünü satışa açık ilanlar görünür. Bu dört koşul tek bir sorguda (`ListingRepository._public_query`)."

## Adım 3 — Üretici: ürün ve ilan (1.5 dk) — normal pencere
1. `uretici1@example.com` ile giriş → **Üretici paneli** (ürün sayısı, düşük stok).
2. **Ürünlerim** → "Salkım Domates": depoda 300 kg.
3. **Yeni ilan** aç: Salkım Domates, fiyat `30`, miktar `500` → **hata:** "Depoda ilana ayrılabilecek en fazla ... kg var".
   Miktarı `20` yap → ilan yayında.

**Söyle:** "Ürün depodaki mal, ilan satışa çıkan kısmı. İlanların toplamı depoyu aşamaz; olmayan malı satmayı engelliyor. Bu, Hafta 6 ürün modülü ile Hafta 7 ilan modülünün entegrasyon noktası."

## Adım 4 — Müşteri: sepet ve sipariş (2 dk) — gizli pencere
1. `musteri@example.com` ile giriş → **İlanlar** → Salkım Domates → miktar `3` → **Sepete ekle**.
2. **Gün Kurusu Kayısı** (Üretici 2) ilanından `1` kg ekle → **Sepet**: kalemler üreticiye göre gruplu.
3. **Siparişe geç** → adres: `Örnek Mah. Deneme Sok. No:5 Merkez / Bingöl` (uydurma) → **Siparişi Oluştur**.
   Mesaj: "Sepetiniz 2 üreticiye ait olduğu için 2 ayrı sipariş oluşturuldu."
4. Domates siparişini aç → **Öde (deneme ödemesi)** → durum "Ödendi · hazırlanıyor".

**Söyle:** "Ödeme adımı tek bir transaction: stok kontrolü, sipariş, fiyatın kopyalanması, iki stoğun düşmesi ve sepetin boşalması. Biri başarısız olursa hepsi geri alınır (rollback). Ödeme şimdilik sahte; Hafta 9'da gerçek API gelecek."

## Adım 5 — Üretici: kargo (45 sn) — normal pencere
1. Sayfayı yenile → panelde "Kargoya verilmeyi bekleyen 1 ödenmiş siparişiniz var" uyarısı.
2. **Gelen siparişler** → siparişi aç → **Kargoya verdim**.
3. **Ürünlerim**: Salkım Domates stoğu 3 kg azaldı.

**Söyle:** "Üretici yalnızca kendi siparişini görür; başka siparişin numarasını adres çubuğuna yazarsa 404 alır."

## Adım 6 — Müşteri: teslim + iptal (45 sn) — gizli pencere
1. Domates siparişi → **Teslim alındı** → son durum.
2. Kayısı siparişi (ödeme bekliyor) → **Siparişi iptal et** → stok geri döner.

**Söyle:** "Durum geçişleri `order_service.TRANSITIONS` tablosunda. Tabloda olmayan geçiş, örneğin teslim edilmiş siparişi iptal etmek, reddedilir."

## Adım 7 — Yönetici paneli (45 sn)
1. Gizli pencerede çıkış → `yonetici@example.com` ile giriş → **Yönetici paneli**.
2. Kullanıcı sayısı (role göre), ürün/açık ilan, sipariş (duruma göre), ciro.
3. **Tümü** → tüm siparişler; birini aç.

**Söyle:** "Bu ekran entegrasyonun özeti: her sayı başka bir modülün tablosundan geliyor. Kullanıcılar Hafta 5'ten, ürünler Hafta 6'dan, ilan ve sipariş Hafta 7'den."

## Adım 8 — Testler ve sürüm (45 sn) — VS Code
1. Terminal: `python -m pytest` → **98 passed**.
2. `tests/test_integration.py` → `test_end_to_end_happy_path`: "Az önce gösterdiğim senaryonun otomatik hâli."
3. `git tag` → `v0.8.0` ve `v0.8.1`; `CHANGELOG.md` → 0.8.0 ve 0.8.1 bölümleri.

**Söyle:** "Bu hafta 4 entegrasyon hatası buldum. Her biri için önce hatayı yakalayan bir regresyon testi yazdım, sonra düzelttim."

---

## Bir şey ters giderse
| Sorun | Çözüm |
|---|---|
| Canlı site açılmıyor / çok yavaş | 1 dakika bekle (uyku modu). Olmazsa yerelde `python run.py` ile devam et |
| Yönetici hesabıyla giriş olmuyor | v0.8.0 henüz canlıya çıkmamış olabilir (`git push` yapıldı mı?). Yerelde `flask seed-demo` ile göster |
| Demo ilanlarının stoğu önceki denemelerde bitmiş | Üretici olarak ilanı düzenleyip miktarı artır (bu da ayrıca bir gösterim olur) |
| Bilgisayarda internet yok | Yerelde çalıştır; tüm özellikler SQLite ile aynı çalışır |
