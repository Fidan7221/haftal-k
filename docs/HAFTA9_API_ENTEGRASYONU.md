# Hafta 9 — Harici API Entegrasyonu: Fiyat ve Ödeme

**Amaç:** Hal fiyatı verisini ve ödeme akışını harici servislerle entegre etmek.
**Sürüm:** `v0.9.0` · **Testler:** `tests/test_api_integration.py`

## 1. Dosyalar

| Dosya | Görevi |
|---|---|
| `app/integrations/http.py` | Ortak HTTP katmanı: timeout, yeniden deneme, 429 (hız sınırı), hata sınıfları |
| `app/integrations/price_api.py` | Hal fiyatı istemcisi (`HalPriceClient` gerçek, `MockPriceClient` sahte) + yanıt doğrulama |
| `app/integrations/payment_api.py` | Ödeme istemcisi (`HttpPaymentGateway` gerçek, `MockPaymentGateway` test modu) |
| `app/services/price_service.py` | Fiyatları çekip `market_prices` tablosuna yazar; sorgular; ürün ↔ hal ürünü eşleştirme |
| `app/services/payment_service.py` | Ödeme akışı ve iade |
| `app/routes/price_routes.py` | `/hal-fiyatlari` sayfası |
| `app/routes/order_routes.py` | `/siparislerim/<id>/odeme` ödeme formu |
| `config.py`, `.env.example`, `render.yaml` | Anahtarlar yalnızca ortam değişkeninde |

Katman kuralı: **Rota → Servis → Entegrasyon → HTTP.** Rotalar hiçbir zaman doğrudan dış servise istek atmaz.

## 2. API anahtarı nerede, nasıl saklanıyor?

- Anahtarlar **kodda ve git deposunda yok**. `config.py` onları `os.environ`'dan okur.
- Yerelde `.env` dosyasında durur (`.gitignore` içinde, git'e gitmez). Şablonu: `.env.example` (değerler boş).
- Canlıda Render panelinde ortam değişkeni olarak girilir (`render.yaml` → `sync: false`, Render kurulumda sorar).
- Fiyat API anahtarı **başlıkta** (`X-API-Key`) gönderilir, adreste (URL) değil. Adresler sunucu günlüklerine yazılır, başlıklar yazılmaz.
- Ödeme API'sinde **gizli anahtar (secret) hiç gönderilmez.** İstek gövdesinin HMAC-SHA256 imzası (`X-Signature`) bu anahtarla üretilir. Sağlayıcı aynı imzayı hesaplayarak isteğin bizden geldiğini ve yolda değişmediğini doğrular.
- Kullanıcıya gösterilen hata mesajlarında (`user_message`) adres, anahtar veya teknik ayrıntı yer almaz. Bu ayrıntılar yalnızca günlüğe yazılır (`detail`).

## 3. Hata yönetimi (`app/integrations/http.py`)

| Durum | Sınıf | Ne yapılır? |
|---|---|---|
| Yanıt `timeout` saniye içinde gelmedi | `ApiTimeoutError` | Geçici: 0,5 sn → 1 sn bekleyip en fazla 2 kez yeniden dener |
| Bağlantı kurulamadı | `ApiConnectionError` | Geçici: yeniden dener |
| 429 Too Many Requests | `ApiRateLimitError` | `Retry-After` başlığı kadar bekler (en fazla 5 sn), yeniden dener |
| 5xx sunucu hatası | `ApiServerError` | Geçici: yeniden dener |
| 401 / 403 | `ApiAuthError` | Kalıcı: **yeniden denenmez** (anahtar yanlış) |
| Diğer 4xx | `ApiClientError` | Kalıcı: yeniden denenmez |
| Yanıt JSON değil / beklenen alan yok | `ApiResponseError` | Kalıcı: veri kullanılmaz |

Hepsi `IntegrationError`'dan türer. Servis katmanı tek bir `except IntegrationError` ile yakalayıp Türkçe mesaj gösterir.

**Yanıt ayrıştırma (`parse_items`):** API'ye körü körüne güvenilmez. Adı boş olan, fiyatı negatif, eksik ya da sayı olmayan, `min ≤ ort ≤ maks` kuralını bozan satırlar atlanır ve sayılır. Sağlayıcı değişirse yalnızca bu fonksiyon değişir.

## 4. Hız sınırı (rate limit) önlemleri

1. Veritabanında zaten olan günler tekrar istenmez (önbellek). `flask fetch-prices --force` ile zorlanabilir.
2. İki fiyat isteği arasında `PRICE_API_MIN_INTERVAL` (0,5 sn) beklenir.
3. Yöneticinin "Fiyatları güncelle" düğmesi en sık dakikada bir çalışır (`PRICE_SYNC_COOLDOWN`).
4. 429 hatasında `Retry-After` kadar beklenir. Yine olmazsa senkronizasyon **durur**; ısrar etmek anahtarın engellenmesine yol açar.

## 5. Ödeme akışı

```
Sepet ──checkout──> Sipariş (ödeme bekleniyor, stok ayrıldı)
                        │
                 müşteri "Öde" → kart formu (Luhn + son kullanma kontrolü; hatalıysa API'ye gitmez)
                        │
        Payment = INITIATED  (commit: dış çağrıdan ÖNCE iz bırak)
                        │
              ödeme API'si (timeout + yeniden deneme + Idempotency-Key)
             ┌──────────┴──────────┐
         başarılı              reddedildi / zaman aşımı / 5xx
   Payment = SUCCESS          Payment = FAILED + hata mesajı
   Sipariş = ÖDENDİ           Sipariş "ödeme bekleniyor"da KALIR
                              → başka kartla tekrar dene veya iptal et (stok geri döner)
```

- **Idempotency-Key:** Zaman aşımında istek yeniden gönderilir. Aynı anahtarla gelen ikinci isteği sağlayıcı yeni bir ödeme saymaz, ilk sonucu döndürür. Bu sayede müşteriden **iki kez para çekilmez.**
- **Kart bilgisi saklanmaz:** Veritabanına ve günlüğe yazılmaz, hata olsa bile forma geri doldurulmaz. Yalnızca sağlayıcının işlem numarası (`transaction_ref`) saklanır. Bunu bir test kontrol ediyor: `test_card_number_is_not_stored`.
- **Ödendi durumu elle seçilemez:** Durum düğmesiyle `paid` gönderilirse reddedilir. Sipariş yalnızca para gerçekten alındığında ödendi olur.
- **İade:** Ödenmiş sipariş iptal edilince önce sağlayıcıdan iade istenir. İade başarısızsa sipariş **iptal edilmez** ve stok geri eklenmez (rollback).

**Test modu kartları** (`USE_MOCK_APIS=1`, gerçek para çekilmez):

| Kart | Sonuç |
|---|---|
| 4111 1111 1111 1111 | Başarılı |
| 4000 0000 0000 0002 | Banka reddeder (yetersiz bakiye) |
| 4000 0000 0000 0119 | Zaman aşımı |
| 4000 0000 0000 0259 | Servis hatası (500) |

## 6. Çalıştırma

```
flask fetch-prices --days 30     # sahte servis: internet gerekmez
python run.py                    # /hal-fiyatlari, sipariş → Öde
python -m pytest tests/test_api_integration.py -v
```

Gerçek servise geçmek için `.env` dosyasında `USE_MOCK_APIS=0` yapılır ve `PRICE_API_URL`, `PRICE_API_KEY`, `PAYMENT_API_URL`, `PAYMENT_API_KEY`, `PAYMENT_SECRET_KEY` doldurulur.

## 7. Sözlü sınav soruları — cevaplarım

1. **Ödeme akışını nasıl kurdun?** Sipariş oluşunca stok ayrılır ve sipariş "ödeme bekleniyor" durumuna geçer. Müşteri kart formunu doldurur; form Luhn ve son kullanma kontrolü yapar. `payment_service.pay_order` önce `INITIATED` kaydı yazar, sonra ödeme API'sini çağırır. Sonuca göre ödeme `SUCCESS` ve sipariş `PAID` olur, ya da ödeme `FAILED` olur. (Bölüm 5)
2. **Ödeme başarısızsa sipariş ne oluyor?** Sipariş iptal edilmez, "ödeme bekleniyor" durumunda kalır ve stok ayrılmış kalır. Ödeme kaydı `FAILED` olur ve hata mesajı siparişte görünür. Müşteri başka kartla tekrar deneyebilir ya da siparişi iptal edebilir; iptalde stok geri eklenir.
3. **API anahtarını nasıl ve nerede sakladın?** Ortam değişkeninde saklıyorum: yerelde `.env` (git'e gitmez), canlıda Render paneli. Kodda yok. Fiyat anahtarı başlıkta gider. Ödemedeki gizli anahtar hiç gönderilmez, yalnızca imza üretir. (Bölüm 2)
4. **API çağrısı başarısızsa ne oluyor?** Geçici hatalarda (timeout, 429, 5xx) bekleyip yeniden denenir. Kalıcı hatalarda (401, 400) hemen vazgeçilir. Her durumda kullanıcı uygulamanın çökmesi yerine anlaşılır bir Türkçe mesaj görür. Fiyat senkronizasyonunda başarısız gün atlanır, diğer günler kaydedilir. (Bölüm 3)
5. **Yanıtı nasıl ayrıştırdın?** `response.json()` ile sözlüğe çeviriyorum. Ardından `parse_items` her satırı doğrular ve `Decimal`'e çevirir; hatalı satırlar atlanır. Ödeme yanıtında `status` ve `id` alanları zorunlu, yoksa `ApiResponseError`. (Bölüm 3)

## 8. Haftalık kontrol kriterleri

- [x] API anahtarı depoda değil (`.env` git'te yok; `.env.example`'da değerler boş)
- [x] Hatalar yönetiliyor (7 hata sınıfı; testler: timeout, 429, 5xx, 401, bozuk JSON)
- [x] Entegrasyon doğru (38 test; ödeme ve fiyat uçtan uca)
