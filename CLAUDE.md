# Tarladan Sofraya — Claude için proje notları

Çiftçi doğrudan satış ve hal fiyatı takip platformu. Bingöl Üniversitesi "Bilgisayar Uygulamaları I"
dersinin haftalık projesi. Kod, yorumlar, belgeler ve kullanıcı arayüzü **Türkçe**; yeni kod da
Türkçe yorumlu ve öğrencinin sözlü sınavda anlatabileceği sadelikte olmalı.

- Sürüm: `0.10.0` (`app/__init__.py` → `__version__`; CHANGELOG ile aynı tutulur)
- Teknoloji: Python 3 + Flask, SQLAlchemy, SQLite (yerel) / PostgreSQL (Render), Bootstrap 5, pytest
- Haftalık ders planı README'deki "Haftalara göre durum" tablosunda. Sıradaki: **Hafta 11 — Değerlendirme ve İtibar Modülü**

## Komutlar

```
python run.py                     # http://127.0.0.1:5000
python -m pytest                  # 181 test, ~3 dk
flask db upgrade                  # migration'lar migrations_flask/ içinde (migrations/ Hafta 4 Node.js'e ait)
flask seed-db / seed-demo / create-admin
flask fetch-prices --days 60      # hal fiyatları (varsayılan sahte servis, internet gerekmez)
python build_exe.py               # masaüstü .exe (masaustu.py)
```

## Mimari kurallar

- Katmanlar: **rota → servis → repository/model**; harici API'ler için **servis → `app/integrations/` → `http.py`**.
  Rotalar hiçbir zaman doğrudan dış servis çağırmaz.
- İş kuralı ihlali: servis `ServiceError(message, field=None)` fırlatır, rota flash veya form alanında gösterir.
- Yetki: `@role_required(RoleName.X)`; başkasının kaydı → 404 (varlığı belli olmasın).
- Sipariş durumları yalnızca `order_service.TRANSITIONS` tablosuyla değişir.
- Gizli anahtarlar yalnızca ortam değişkeninde (`.env`, Render paneli). Koda, testlere, belgelere yazılmaz.
- Testler internete çıkmaz ve para harcamaz: `TestingConfig` → `USE_MOCK_APIS=True`, `AI_ENABLED=False`.
- Her haftanın sonunda: `docs/HAFTAn_*.md` (sözlü sınav soruları + cevaplar + kontrol kriterleri),
  CHANGELOG girdisi, README tablosu satırı, `docs/AI_KULLANIM_GUNLUGU.md` satırı.

## Hafta 9 — Harici API (fiyat + ödeme) — yapılanlar ve kararlar

- `app/integrations/http.py`: tüm dış istekler buradan. Her istekte timeout; timeout/bağlantı/429/5xx
  geçici sayılır, üstel bekleme ile en fazla 2 kez tekrar; 429'da `Retry-After` (en fazla 5 sn);
  401/403/4xx kalıcı, tekrar denenmez. Hatalar `IntegrationError` alt sınıfları; `detail` günlük için,
  `user_message` kullanıcıya gösterilecek güvenli Türkçe metin.
- `price_api.py`: `HalPriceClient` (gerçek, anahtar `X-API-Key` başlığında) + `MockPriceClient`
  (deterministik sahte veri, 11 ürün). Yanıt `parse_items` ile doğrulanır; hatalı satırlar atlanır.
  **Gerçek sağlayıcı henüz seçilmedi**; yanıt biçimi varsayımdır, sağlayıcı değişirse yalnızca `parse_items` uyarlanır.
- `payment_api.py`: `HttpPaymentGateway` (HMAC-SHA256 imza `X-Signature`, gizli anahtar gönderilmez,
  `Idempotency-Key` ile çift çekim önlenir) + `MockPaymentGateway` (test modu kartları:
  4111…1111 başarılı, 4000…0002 red, 4000…0119 zaman aşımı, 4000…0259 servis hatası).
- `price_service.py`: senkronizasyon (olan günleri tekrar çekmez, istekler arası bekleme, yönetici
  düğmesi dakikada bir), sorgular, ürün ↔ hal ürünü eşleştirme (`match_market_name`: kelime başı
  eşleşmesi, en fazla 2 harf ek — "Çiçek Balı"→"Bal", ama "Balkabağı" eşleşmez).
- `payment_service.py` ödeme akışı: önce `Payment=INITIATED` commit, sonra API. Başarısızsa
  `FAILED` + mesaj, **sipariş "ödeme bekleniyor"da kalır**, tekrar denenebilir (aynı Payment satırı güncellenir).
  İptalde önce iade; **iade başarısızsa sipariş iptal edilmez** (rollback).
- **Karar:** Sipariş artık durum düğmesiyle `paid` yapılamaz (eski `_mock_payment` kaldırıldı);
  yalnızca `/siparislerim/<id>/odeme` kart formuyla. Eski testlerdeki `set_status(PAID)` yardımcıları
  kart formunu kullanacak şekilde değiştirildi.
- Kart bilgisi veritabanına/günlüğe yazılmaz, forma geri doldurulmaz. Form Luhn + son kullanma kontrol eder.
- Sayfalar: `/hal-fiyatlari` (herkese açık), yönetici `POST /yonetici/fiyatlar/guncelle`.
- `render.yaml`: açılışta `flask fetch-prices --days 60`; `USE_MOCK_APIS=1`, `ANTHROPIC_API_KEY` (sync: false).

## Hafta 10 — Yapay zekâ bileşeni — yapılanlar ve kararlar

- Sağlayıcı: **Anthropic Claude**, resmi `anthropic` Python SDK'sı (1.17 kurulu), model `claude-opus-5-5`
  (`AI_MODEL` ile değişir). Anahtar `ANTHROPIC_API_KEY`; yoksa bileşen kapalı ve kural tabanlı öneri kullanılır.
- `app/ai/trend.py` (yapay zekâsız): son 21 güne doğrusal regresyon, R², oynaklık, 7 gün tahmini;
  ±%3 eşiğiyle up/down/stable; `rule_based_advice` yedek ve karşılaştırma ölçüsü.
- `app/ai/llm_advisor.py`: sabit `SYSTEM_PROMPT` + `build_prompt` (seri + hesaplanan göstergeler),
  `PROMPT_VERSION="v1"`. Çağrı: `client.beta.messages.create` + `output_config` (JSON şeması, `effort: "low"`)
  + `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` (refusal'da yedek model).
  `validate_output` çıktıyı kendi kurallarıyla denetler (geçersiz trend, %25'ten uzak fiyat, 0–1 dışı güven,
  boş/bağlantılı metin, iç çelişki, verilerle güçlü çelişki → red; hafif fark → güven ≤0,5 + uyarı).
- `app/services/ai_service.py`: hatalı/boş/kesik çıktı, refusal, timeout, API hatası → kural tabanlı öneri ve
  sebebi ekranda. Aynı ürün aynı gün tekrar sorulursa kayıtlı tahmin (API çağrılmaz); yenileme günde en fazla 5.
  Sonuç `price_predictions` tablosuna; istem/ham çıktı/doğrulama `instance/ai_gunlugu.jsonl`'a (`AI_LOG_PATH`).
- Modele kişisel veri gönderilmez (yalnızca ürün türü ve hal fiyatları).
- Sayfalar: üretici `/uretici/urunler/<id>/fiyat-onerisi` (Ürünlerim'deki 📈 düğmesi), yönetici `/yonetici/ai-gunlugu`.
- Testlerde `llm_advisor.create_client` sahte istemciyle değiştirilir (monkeypatch).

## Bilinen açık noktalar

- Claude API'ye **gerçek bir istek hiç atılmadı** (anahtar yok, para harcanmasın diye); yalnızca sahte istemciyle test edildi.
- Masaüstü .exe paketine `anthropic` eklenmedi; orada yapay zekâ kapalı, kural tabanlı çalışır.
  `masaustu.py` AI günlüğünü veri klasörüne yazar ve açılışta 60 günlük örnek fiyat yükler.
- `docs/AI_KULLANIM_GUNLUGU.md` Hafta 9-10 satırlarındaki "Benim katkım" sütunu öğrenci tarafından
  doldurulacak — öğrenci adına doğrulama iddiası **uydurulmamalı**.
- Hafta 9-10 değişiklikleri commit edilmedi; commit ve `git tag` öğrencinin işi.
- Şema değişikliği yapılmadı (mevcut `payments`, `market_prices`, `price_predictions` tabloları kullanıldı); migration gerekmedi.
