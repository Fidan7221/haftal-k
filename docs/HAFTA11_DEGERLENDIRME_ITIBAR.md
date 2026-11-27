# Hafta 11 — İleri Modül: Değerlendirme ve İtibar Modülü

**Amaç:** Üretici/ürün değerlendirme ve itibar modülünü geliştirmek.
**Sürüm:** `v0.11.0` · **Testler:** `tests/test_reviews.py` (39 test)

## 1. Dosyalar

| Dosya | Görevi |
|---|---|
| `app/models/review.py` | `Review` modeli (Hafta 3'ten beri hazır; Hafta 11'de kullanılmaya başlandı) |
| `app/models/producer.py` | `reputation_score`, `review_count`: itibarın önbelleği |
| `app/repositories/review_repository.py` | Değerlendirme sorguları (tek veri erişim noktası) |
| `app/services/review_service.py` | **Modülün çekirdeği:** iş kuralları, içerik denetimi, itibar hesabı |
| `app/forms/shop_forms.py` → `ReviewForm` | Puan (1-5) ve yorum formu |
| `app/routes/order_routes.py` → `review_item` | Müşteri: `POST /siparislerim/<id>/kalem/<kalem>/degerlendir` |
| `app/routes/producer_routes.py` → `reviews` | Üretici: `/uretici/degerlendirmeler` |
| `app/routes/admin_routes.py` → `reviews`, `toggle_review` | Yönetici: `/yonetici/degerlendirmeler` (gizle / yayına al) |
| Şablonlar | Sipariş detayında form; ilan sayfasında yorumlar ve puan; ilan kartında üretici puanı |
| `flask recompute-reputation` | Tüm itibar puanlarını yeniden hesaplar |

## 2. Veri modeli

```
users (müşteri) ──1:N──┐
                        ├── reviews ──N:1── producer_profiles (itibar önbelleği: reputation_score, review_count)
order_items ──1:0..1────┘      │
                               rating  INTEGER  CHECK (rating BETWEEN 1 AND 5)
                               comment TEXT
                               is_visible BOOLEAN (yönetici gizleyebilir)
                               order_item_id UNIQUE  → her kaleme en fazla 1 yorum
```

- Yorum ürüne değil **sipariş kalemine** bağlı. Satın almadan yorum yapmak yapısal olarak imkânsız; hangi siparişten, ne zaman, hangi fiyattan alındığı da bilinir.
- Ürünün puanı ayrıca saklanmaz; `reviews → order_items → listings → products` birleştirmesiyle sorgulanır.
- Üreticinin itibarı her yorumda yeniden hesaplanıp profilde **önbellek** olarak tutulur. Böylece her ilan kartında puanı göstermek için tüm yorumları okumak gerekmez.
- Yeni tablo veya sütun eklenmedi; şema Hafta 3'te bu hafta düşünülerek kurulmuştu (`flask db check`: fark yok).

## 3. İş kuralları ve doğrulama

Kurallar **üç katmanda** uygulanır. Form kullanıcıya hızlı geri bildirim verir. Servis asıl kuralları uygular, çünkü form atlanabilir. Veritabanı son güvencedir.

| # | Kural | Nerede |
|---|---|---|
| 1 | Yalnızca **siparişi veren müşteri** yorum yapar; başkasının siparişi → 404, üretici/yönetici → 403 | rota + `review_problem` |
| 2 | Sipariş **teslim edilmiş** olmalı (bekleyen, ödenmiş, kargodaki, iptal → olmaz) | `review_problem` |
| 3 | Teslimden sonra en fazla **30 gün** içinde | `review_problem` |
| 4 | Her sipariş kalemine **tek yorum** | servis + veritabanı `UNIQUE` |
| 5 | Puan **1-5 tam sayı** (`True` gibi değerler de reddedilir) | form + servis + veritabanı `CHECK` |
| 6 | **1-2 yıldızda en az 15 karakter gerekçe** | `content_problem` |
| 7 | Yorum en fazla 500 karakter | form + servis |

**Erişim ve sahiplik:** Kalem, URL'deki siparişin içinde değilse 404 döner; başka siparişin kalemi yazılarak yorum yapılamaz.

## 4. Kötüye kullanım önleme (sahte değerlendirmeyi azaltma)

| Önlem | Neyi engelliyor |
|---|---|
| **Doğrulanmış satın alma** (kural 1-2) | Alışveriş yapmadan, sahte hesapla yorum |
| **Her müşteri tek oy** (itibar hesabında) | Aynı kişinin çok sipariş verip puanı şişirmesi veya batırması |
| **Bayes ortalaması** | Birkaç (sahte olabilecek) yorumla puanın 5,0'a veya 1,0'a fırlaması |
| **Günlük sınır** (24 saatte 10 yorum) | Toplu, otomatik yorum |
| **İçerik denetimi** | Bağlantı (reklam/oltalama), telefon ve e-posta (kişisel veri, KVKK), `!!!!!!` gibi tekrar, tamamı büyük harf |
| **Gerekçesiz düşük puan yasağı** | Nedensiz "1 yıldız" ile üreticiyi cezalandırma |
| **Yönetici moderasyonu** | Uygunsuz yorum gizlenir (silinmez), itibara katılmaz, gerekirse geri alınır |
| **Gizlilik** | İlan sayfasında müşterinin yalnızca adının ilk kelimesi görünür |

## 5. İtibar hesabı

```
itibar = (C × m + Σ müşteri_oyları) / (C + müşteri_sayısı)

müşteri_oyu = o müşterinin bu üreticiye verdiği puanların ortalaması   (her müşteri TEK oy)
m           = platformdaki tüm görünür yorumların ortalaması (yorum yoksa 4,0)
C           = 5  → "5 müşteri görmeden ortalamaya tam güvenme"
```

| Durum | Basit ortalama | Bizim itibar (m = 4,0) |
|---|---|---|
| 1 müşteri, 5 yıldız | 5,00 | **4,17** |
| 20 müşteri, ortalama 4,8 | 4,80 | **4,64** |
| 1 müşteri 10 kez 1 yıldız + 2 müşteri 5 yıldız | 1,67 | **3,88** |

- Yalnızca **görünür** yorumlar hesaba katılır.
- Platform ortalaması her yorumla değiştiği için yorumu olan **tüm** üreticilerin puanı birlikte güncellenir (`refresh_reputations`).
- Hesap saf bir fonksiyonda (`compute_reputation`); veritabanına dokunmadığı için doğrudan test edilebiliyor.

## 6. Diğer modüllerle entegrasyon

- **Sipariş (Hafta 7):** Değerlendirme yalnızca `delivered` durumunda açılır; sipariş detayında her kalem için form ya da verilen yorum görünür.
- **İlan / Pazar (Hafta 7):** İlan sayfasında üretici itibarı, ürün puanı ve son 10 yorum ("Satın aldı" etiketiyle); ilan kartlarında ★ puan.
- **Üretici paneli (Hafta 6):** "İtibar puanı" kartı artık gerçek değeri gösteriyor ve değerlendirmeler sayfasına götürüyor.
- **Yönetici paneli (Hafta 8):** "Değerlendirmeler" kartı → moderasyon sayfası.
- **Kimlik ve yetki (Hafta 5):** `@role_required` + sahiplik kontrolü.
- **İlişkili kayıtlar:** Ürün siparişte olduğu için silinemez, arşivlenir (Hafta 8). Bu yüzden yorumlar sahipsiz kalmaz. Yorum gizlendiğinde itibar yeniden hesaplanır.

## 7. Çalıştırma

```
python run.py
# Müşteri: Siparişlerim → teslim edilmiş sipariş → "Ürünleri değerlendirin"
# Herkes:  Pazar → ilan → "Değerlendirmeler"
# Üretici: Panelim → İtibar puanı → "Değerlendirmeleri gör"
# Yönetici: Yönetici paneli → "Değerlendirmeler" → Gizle / Yayına al
flask recompute-reputation
python -m pytest tests/test_reviews.py -v
```

## 8. Sözlü sınav soruları — cevaplarım

1. **İtibarı nasıl hesapladın?** Bayes ortalamasıyla (Bölüm 5). Önce her müşterinin bu üreticiye verdiği puanların ortalamasını alıp tek oy yapıyorum. Sonra platform ortalamasından 5 "sanal oy" ekliyorum. Az yorumu olan üretici ortalamaya yakın kalır, yorum arttıkça gerçek puanına yaklaşır. Yalnızca görünür yorumlar sayılır.
2. **Sahte değerlendirmeyi nasıl azalttın?** En güçlü önlem doğrulanmış satın alma: yorum sipariş kalemine bağlı ve yalnızca teslim edilmiş siparişin sahibi yorum yapabiliyor. Buna ek olarak her müşteri tek oy, Bayes ortalaması, günlük sınır, içerik denetimi ve yönetici moderasyonu var (Bölüm 4).
3. **Bu modülün verisini nasıl modelledin?** `reviews` tablosu sipariş kalemine 1-1 (UNIQUE), müşteriye ve üreticiye N-1 bağlı. Puan için CHECK kısıtı var. İtibar üretici profilinde önbellek olarak tutuluyor, ürün puanı sorguyla hesaplanıyor (Bölüm 2).
4. **Bu modülde hangi iş kuralını neden koydun?** Örnekler: "Teslim edilmeden yorum yok", çünkü ürünü görmeden değerlendirme olmaz. "1-2 yıldızda gerekçe zorunlu", çünkü üretici sorunu ancak böyle düzeltebilir ve nedensiz düşük puan zorlaşır. "Telefon/e-posta yasak", çünkü yorumlar herkese açık ve bunlar kişisel veri (Bölüm 3-4).
5. **Bu modülü diğer modüllerle nasıl entegre ettin?** Sipariş durum makinesine (yalnızca `delivered`), ilan sayfası ve kartlarına, üretici ve yönetici panellerine, rol ve sahiplik kontrollerine bağlandı (Bölüm 6). Entegrasyon testleri gerçek kullanıcı gibi ilan → sipariş → ödeme → kargo → teslim → değerlendirme yolunu baştan sona dener.

## 9. Haftalık kontrol kriterleri

- [x] Değerlendirme ve İtibar Modülü çalışıyor (39 test; uçtan uca akış)
- [x] Doğrulama ve iş kuralları uygulanıyor (form + servis + veritabanı kısıtları)
- [x] Önceki modüllerle tutarlı (sipariş durumu, ilan, paneller, yetki; toplam 230 test geçiyor)
