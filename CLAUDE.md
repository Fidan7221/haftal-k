# Tarladan Sofraya — Claude için proje notları

Çiftçi doğrudan satış ve hal fiyatı takip platformu. Bingöl Üniversitesi "Bilgisayar Uygulamaları I"
dersinin haftalık projesi. Kod, yorumlar, belgeler ve kullanıcı arayüzü **Türkçe**; yeni kod da
Türkçe yorumlu ve öğrencinin sözlü sınavda anlatabileceği sadelikte olmalı.

- Sürüm: `0.12.1` (`app/__init__.py` → `__version__`; CHANGELOG ile aynı tutulur)
- Teknoloji: Python 3 + Flask, SQLAlchemy, SQLite (yerel) / PostgreSQL (Neon; web servisi Render'da), Bootstrap 5, pytest
- Haftalık ders planı README'deki "Haftalara göre durum" tablosunda. Sıradaki: **Hafta 13 — Test ve Hata Ayıklama**

## Komutlar

```
python run.py                     # http://127.0.0.1:5000
python -m pytest                  # 249 test, ~3 dk
flask db upgrade                  # migration'lar migrations_flask/ içinde (migrations/ Hafta 4 Node.js'e ait)
flask seed-db / seed-demo / create-admin
flask remove-demo-listings        # demo ilanlarını Pazar'dan kaldırır (Render açılışında çalışır)
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
- `render.yaml`: açılışta `flask fetch-prices --days 60`; `USE_MOCK_APIS=1`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` (sync: false).

## Hafta 10 — Yapay zekâ bileşeni — yapılanlar ve kararlar

- İki sağlayıcı (`AI_PROVIDER`; boşsa `GEMINI_API_KEY` doluysa gemini, değilse anthropic):
  - **Google Gemini** `gemini-3.5-flash-lite` (ücretsiz katman, `GEMINI_API_KEY`): `call_gemini`, REST, Hafta 9'daki
    `request_json` ile; şema reddedilirse (400) şemasız bir kez daha dener. Testlerde `gemini_request` monkeypatch'lenir.
  - **Anthropic Claude** `claude-opus-5-5` (ücretli, `ANTHROPIC_API_KEY`): `call_anthropic`, resmi `anthropic` SDK'sı (1.17).
  - Anahtar yoksa bileşen kapalı ve kural tabanlı öneri kullanılır. `TestingConfig` sağlayıcıyı anthropic'e sabitler.
  - Gemini'de `thinkingLevel: minimal`, tek deneme, `AI_TIMEOUT = 60` (gemini-3.8-flash canlıda 30 sn'de yanıt veremedi). Canlıda gunicorn `timeout = 120` (`gunicorn.conf.py`);
    30 sn'lik varsayılan, yapay zekâ çağrısını kesip 503 veriyordu.
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

## v0.10.4-0.10.5 — Fotoğraflar veri tabanında

- Ürün fotoğrafları veri tabanında: `ProductImage` (`product_images`, `data` deferred, migration `a7d3e9f1b204`).
  Ürün `image_path = "db/<id>"`; `app/utils/uploads.py` kaydet/sil, `/urun-resmi/<id>` sunar, şablonda
  `product_image_url()` global'i. `demo/...` (git'teki örnek) ve eski `products/...` disk yolları da çalışır;
  kaybolmuş disk dosyası → yer tutucu. Sebep: Render ücretsiz planında disk geçici (güncellemede ve 15 dk boşta
  kalıp uyanınca silinir).
- `migrations_flask/env.py`: SQLite PRAGMA'dan sonra `connection.commit()` (yoksa yerel upgrade geri alınıyordu).
- Yapay zekâ **fotoğraf incelemesi** 0.10.4'te eklendi, öğrencinin isteğiyle 0.10.5'te KALDIRILDI; geri ekleme.
  Yapay zekâ ile ürün görseli üretme de istenmedi (Gemini'de ücretsiz değil, alıcıyı yanıltabilir).

## v0.10.8 — Veri tabanı Neon'da

- Render'ın ücretsiz PostgreSQL'i 30 günde siliniyordu (1 Aralık 2026). Veriler Neon'a (neon.tech, ücretsiz,
  süresi dolmaz, AWS US East 2) kopyalandı; eski Render veri tabanına dokunulmadı. `render.yaml`'da artık
  veri tabanı yok; `DATABASE_URL` Render panelinde (sync: false). Neon adresinde `-pooler` YOK (doğrudan bağlantı).
- Taşıma bir kerelikti (geçici betik, repoda değil). `tasima.env` (.gitignore'da) parola içerir; iş bitince silinmeli.

## Hafta 11 — Değerlendirme ve İtibar (v0.11.0)

- Şema değişmedi (reviews, producer_profiles.reputation_score/review_count Hafta 3'ten beri vardı).
- `review_service.py`: `review_problem` (sahiplik, delivered, 30 gün, tek yorum), `content_problem`
  (1-2★ gerekçe ≥15, e-posta/telefon > bağlantı > tekrar > büyük harf sırasıyla), `create_review` (günlük 10),
  `set_visibility` (yönetici), `compute_reputation` (saf; her müşteri tek oy + Bayes C=5, m=platform ortalaması),
  `refresh_reputations` (platform ortalaması değiştiği için yorumu olan TÜM üreticiler güncellenir).
- Teslim zamanı ayrı sütun değil: `order.updated_at` (delivered son durum, sonra değişmez).
- Yorumda müşterinin yalnızca adının ilk kelimesi gösterilir (KVKK); yönetici tam adı görür.

## Hafta 12 — Satış raporu ve bildirimler (v0.12.0)

- `report_service.py`: ciro = Σ qty×unit_price, yalnızca SALE_STATUSES (paid/shipped/delivered) — Hafta 8
  `StatsRepository` ciro kuralıyla AYNI (testte eşitlik var). Toplamlar/top ürünler SQL GROUP BY; günlük seri
  Python'da Türkiye günü (sabit UTC+3, `TR`), boş gün 0. Miktar birime göre ayrı. Önceki dönem 0 ise % yok (None).
  `bar_chart` y ekseni 0'dan. CSV: BOM, `;`, ondalık virgül, `_safe_cell` (=,+,-,@ başına ').
- `notification_service.py` + `notifications` tablosu (migration `c4e7a19d3b60`). `notify()` commit ETMEZ;
  tetikleyiciler: payment_service.pay_order (paid→üretici), order_service.change_status (shipped/delivered/cancelled
  karşı tarafa), checkout (stok eşiği 5, yalnızca ilk geçişte), review_service (yeni yorum). Pending'e bildirim yok.
  `/bildirimler/<id>` yalnızca "/..." (ama "//" değil) adrese yönlendirir.
- `tr_time` şablon filtresi: UTC kayıtları Türkiye saatinde gösterir.

## Bilinen açık noktalar

- Yapay zekâya (Gemini veya Claude) **gerçek bir istek hiç atılmadı**: ne yerelde `.env` ne de (bilindiği kadarıyla) Render'da anahtar var.
  Yalnızca sahte istemciyle test edildi. Ücretsiz yol: aistudio.google.com'dan `GEMINI_API_KEY` alınıp Render'a girilmesi.
- Masaüstü .exe paketine `anthropic` eklenmedi; orada yapay zekâ kapalı, kural tabanlı çalışır.
  `masaustu.py` AI günlüğünü veri klasörüne yazar ve açılışta 60 günlük örnek fiyat yükler.
- `docs/AI_KULLANIM_GUNLUGU.md` "Benim katkım" sütununa yalnızca öğrencinin GERÇEKTEN yaptığı işler yazılır;
  öğrenci adına doğrulama iddiası **uydurulmamalı**.
- Canlıda demo ilanları kaldırıldı (`flask remove-demo-listings`); Pazar'daki ilanlar öğrencinin (fidan) kendi ilanları.
- Gerçek hal fiyatı kaynağı yok: İBB'nin servisi (halfiyatlaripublicdata.ibb.gov.tr) yanıt vermiyor/belgesiz;
  fiyatlar sahte serviste (araştırma: `docs/HAFTA9_API_ENTEGRASYONU.md`).
- Git akışı: değişiklikler `main`'e push edilince Render canlıyı yeniden kurar; etiketler açıklamalı (`git tag -a`).
- Şema değişikliği yapılmadı (mevcut `payments`, `market_prices`, `price_predictions` tabloları kullanıldı); migration gerekmedi.
