# Hafta 12 — Raporlama ve Bildirim: Satış Raporu ve Bildirimler

**Amaç:** Satış istatistikleri ve bildirim modülünü geliştirmek.
**Sürüm:** `v0.12.0` · **Testler:** `tests/test_reports.py` (19 test)

## 1. Dosyalar

| Dosya | Görevi |
|---|---|
| `app/services/report_service.py` | Metrikler, toplulaştırma sorguları, günlük seri, grafik ölçüleri, özet metni, CSV |
| `app/services/notification_service.py` | Bildirim tetikleyicileri ve okuma işlemleri |
| `app/models/notification.py` | `notifications` tablosu (migration `c4e7a19d3b60`) |
| `app/routes/report_routes.py` | `/uretici/rapor`, `/yonetici/rapor`, `.csv` dışa aktarma, `/bildirimler` |
| `app/templates/reports/sales.html` | Rapor sayfası: kartlar, özet, günlük ciro grafiği (SVG), en çok satanlar |
| `app/templates/notifications/list.html` | Bildirim listesi; menüde 🔔 ve okunmamış sayısı |
| Bağlantı noktaları | `payment_service.pay_order`, `order_service.checkout/change_status`, `review_service.create_review` |

## 2. Satış metrikleri: hangileri, neden?

| Metrik | Hesap | Neden bu metrik? |
|---|---|---|
| **Ciro** | Σ (miktar × birim fiyat), yalnızca **ödendi / kargoda / teslim** | Üreticinin gerçekten kazandığı para. Bekleyen sipariş henüz para getirmedi, iptal edilen iade edildi. Hafta 8'deki yönetici panelinin ciro kuralıyla aynı (test: iki ekran aynı sonucu veriyor) |
| **Sipariş sayısı** | Ciroya giren siparişler | Ciroyla birlikte "az sayıda büyük sipariş mi, çok sayıda küçük mü" sorusunu cevaplar |
| **Ortalama sipariş** | Ciro / sipariş | Fiyat ve en az sipariş miktarı kararları için. Sipariş yoksa "—" (sıfıra bölme yok) |
| **İptal oranı** | İptal / (satış + iptal) | Stok veya teslimat sorununun işareti. Bekleyenler henüz sonuçlanmadığı için paydada yok. %20 ve üstü kırmızı uyarı |
| **En çok satanlar** | Ürün başına **ciro** (ilk 5) | Miktar değil ciro: kg ile adet karşılaştırılamaz, TL karşılaştırılabilir |
| **Satılan miktar** | **Birime göre ayrı** (kg, adet…) | "8 kg + 2 adet = 10" yanlış toplulaştırma olurdu |
| **Önceki döneme göre** | Aynı uzunluktaki önceki dönemle % değişim | Tek başına bir sayı "iyi mi kötü mü" söylemez; karşılaştırma söyler |
| **Bekleyen ödeme** | Sayı ve tutar, ciroya dahil değil | Üretici ne kadar paranın yolda olduğunu görsün |

Dönem: son 7 / 30 / 90 gün (`?gun=`), Türkiye saatiyle bugün dahil tam günler.

## 3. Toplulaştırma sorguları

```sql
-- Durum başına sipariş sayısı ve tutar (toplamlar, ortalama, iptal oranı bundan çıkar)
SELECT orders.status, COUNT(DISTINCT orders.id), SUM(order_items.quantity * order_items.unit_price)
FROM order_items JOIN orders ON order_items.order_id = orders.id
WHERE orders.created_at >= :baslangic AND orders.created_at < :bitis AND order_items.producer_id = :uretici
GROUP BY orders.status;

-- En çok ciro getiren 5 ürün
SELECT products.name, products.unit, SUM(quantity), SUM(quantity * unit_price) AS ciro
FROM order_items JOIN orders ... JOIN listings ... JOIN products ...
WHERE orders.status IN ('paid','shipped','delivered') AND ...
GROUP BY products.id ORDER BY ciro DESC LIMIT 5;
```

- Toplamlar veritabanında `GROUP BY` ile hesaplanır; Python'a yalnızca birkaç satır gelir.
- **Günlük seri Python'da:** Kayıtlar UTC saklanıyor. Günleri **Türkiye saatine** göre ayırmak gerekiyor; UTC ile gruplansaydı gece 00:00–03:00 arasındaki satışlar bir önceki güne yazılırdı (test: `test_days_are_grouped_by_turkey_time`). SQLite ve PostgreSQL'in tarih fonksiyonları farklı olduğu için de bu kısım Python'da daha taşınabilir.
- **Eksik veri:** Satış olmayan günler 0 olarak eklenir. Atlansaydı grafikte boşluk görünmez, eğilim olduğundan farklı görünürdü.
- **Kesirli sayılar:** Para `Decimal` ile hesaplanır; `float` yuvarlama hatası yapar (0,1 + 0,2 ≠ 0,3).

## 4. Görselleştirme

- **Günlük ciro:** Çubuk grafik (SVG, harici kütüphane yok). Y ekseni **her zaman 0'dan başlar**. 0'dan başlamayan eksen küçük farkları büyük gösterir; bu, en yaygın yanıltıcı görsel hatası. Çubuğun üstüne gelince tarih ve tutar görünür. Ekran okuyucular için `aria-label` var.
- **En çok satanlar:** Yatay çubuklar; en büyüğe göre oranlanır, tutar yanında yazılı.
- **Özet metni:** Rapordaki sayılardan kurallarla üretilen tek paragraf, örneğin "Son 30 günde 4 siparişten 680,00 TL ciro…". Yapay zekâ kullanılmaz; sayılar doğrudan raporun kendisinden gelir.
- **Yönetici:** Aynı rapor tüm platform için, ek olarak "üreticiye göre ciro" tablosu.

## 5. Bildirimler: neye göre tetikleniyor?

| Olay | Kime | Neden |
|---|---|---|
| Sipariş **ödendi** | Üretici | Hazırlamaya başlama zamanı. Bekleyen siparişe bildirim yok: ödeme gelmeyebilir, üretici boşuna hazırlanmasın |
| Sipariş **kargoya verildi** | Müşteri | Ürününün yolda olduğunu bilsin |
| Sipariş **teslim edildi** | Müşteri + üretici | Müşteriye **değerlendirme daveti** (Hafta 11 ile bağlantı); üreticiye bilgi |
| Sipariş **iptal edildi** | **Karşı taraf** | İşlemi yapan kişiye gönderilmez; ödenmiş siparişte "ödeme iade edildi" yazar |
| İlan stoğu **eşiğin (5) altına indi** / **bitti** | Üretici | Yalnızca eşik **ilk kez** aşıldığında; her satışta tekrar etmez |
| **Yeni değerlendirme** | Üretici | İtibarını takip etsin |

- **Aynı işlem (transaction):** Bildirim olayla birlikte kaydedilir. İade başarısız olup iptal geri alınırsa "iptal edildi" bildirimi de oluşmaz (test: `test_failed_refund_creates_no_notification`).
- **Güvenlik:** Kullanıcı yalnızca kendi bildirimini açabilir (başkasınınki 404). Bildirime tıklayınca yalnızca site içi adrese gidilir; `//başka-site` gibi bir adres varsa gidilmez (açık yönlendirme önlemi).
- **Zamanlama:** Bildirimler olay anında oluşur; zamanlanmış görev (ör. günlük özet e-postası) yok. Render'ın ücretsiz planında site uyuduğu için zamanlanmış iş güvenilir çalışmazdı. E-posta göndermek için ayrıca bir e-posta servisi ve anahtarı gerekirdi.

## 6. Dışa aktarma (CSV)

- **"CSV indir":** Dönemdeki tüm sipariş kalemleri; durum ve "Ciroya dahil: Evet/Hayır" sütunlarıyla.
- **Excel uyumu:** UTF-8 BOM (Türkçe harfler doğru görünsün), `;` ayraç ve ondalık virgül (Türkçe Excel'in beklediği biçim).
- **Formül enjeksiyonu önlemi:** Ürün adı gibi kullanıcıdan gelen bir metin `=`, `+`, `-` veya `@` ile başlıyorsa Excel onu formül sanıp çalıştırabilir. Böyle hücrelerin başına `'` eklenir (test: `test_csv_export`).

## 7. Yanlış veya eksik veri sonucu nasıl etkiler?

| Durum | Sonuç | Önlem |
|---|---|---|
| Bekleyen/iptal sipariş ciroya sayılsaydı | Ciro olduğundan büyük görünür | Yalnızca ödenmiş durumlar sayılır |
| kg ile adet toplansaydı | Anlamsız "satılan miktar" | Birime göre ayrı |
| Satışsız günler atlansaydı | Grafik sürekli satış varmış gibi görünür | Boş gün = 0 |
| UTC ile gün ayrılsaydı | Gece satışları yanlış güne yazılır | Türkiye saati |
| Önceki dönem 0 iken yüzde hesaplansaydı | "Sonsuz %" ya da hata | "önceki dönemde yok" yazılır |
| Ürünün fiyatı sonradan değişseydi | Geçmiş ciro değişirdi | Siparişteki **dondurulmuş** birim fiyat kullanılır (Hafta 7) |
| Y ekseni 0'dan başlamasaydı | Küçük farklar büyük görünür | Eksen her zaman 0 |

## 8. Çalıştırma

```
flask db upgrade          # notifications tablosu (Render'da açılışta kendiliğinden)
python run.py
# Üretici: menü → Rapor (Son 7 / 30 / 90 gün, CSV indir) · menü → 🔔
# Yönetici: menü → Rapor (platform geneli, üreticiye göre ciro)
python -m pytest tests/test_reports.py -v
```

## 9. Sözlü sınav soruları — cevaplarım

1. **Hangi satış metriğini seçtin?** Ana metrik ciro. Yalnızca ödemesi alınmış siparişlerden hesaplanıyor, çünkü üreticinin gerçekten kazandığı parayı gösteriyor. Yanında sipariş sayısı, ortalama sipariş, iptal oranı, en çok satanlar ve önceki döneme göre değişim var (Bölüm 2).
2. **Bildirimleri neye göre tetikledin?** Sipariş yaşam döngüsündeki durum değişikliklerine (ödendi, kargoda, teslim, iptal), stok eşiğinin ilk kez aşılmasına ve yeni değerlendirmeye göre. Bildirim her zaman işlemi yapan kişiye değil, haberi olması gereken kişiye gidiyor (Bölüm 5).
3. **Hangi metrikleri neden seçtin?** Üreticinin vereceği kararlara göre seçtim: fiyat (ortalama sipariş), stok (en çok satanlar, birime göre miktar), sorun tespiti (iptal oranı), gidişat (önceki döneme göre) (Bölüm 2 tablosu).
4. **Görseli hangi veriden ürettin?** Günlük ciro grafiği: ödenmiş siparişlerin kalemleri Türkiye gününe göre toplanıyor, boş günler 0 ekleniyor, Y ekseni 0'dan başlıyor. En çok satanlar: ürün başına ciro, `GROUP BY` sorgusuyla (Bölüm 3-4).
5. **Yanlış/eksik veri sonucu nasıl etkiler?** Bölüm 7'deki tablo. Örneğin iptal edilen sipariş ciroya sayılsaydı ciro yanlış yüksek görünürdü; satışsız günler atlansaydı grafik yanıltırdı. Bunların her biri için test var.

## 10. Haftalık kontrol kriterleri

- [x] Hesaplar doğru (durum filtresi, birim ayrımı, Türkiye günü, önceki dönem, Hafta 8 ciroyla tutarlılık; testli)
- [x] Görseller okunaklı (0'dan başlayan eksen, eksen etiketleri, çubuk üstü bilgi, boş gün = 0)
- [x] Bildirim ve dışa aktarma çalışıyor (6 tetikleyici, zil sayacı, okundu; Excel uyumlu ve güvenli CSV)
