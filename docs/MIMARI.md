# Mimari Şema (Hafta 3)

**Proje:** Çiftçi Doğrudan Satış ve Fiyat Takip Platformu
**Teknoloji:** Python + Flask, SQLAlchemy (ORM), SQLite, Bootstrap 5

## 1. Katmanlı mimari

```
 Tarayıcı (kullanıcı)
        │  HTTP isteği (GET / POST + CSRF)
        ▼
┌───────────────────────────────────────────────┐
│ SUNUM KATMANI                                 │
│ app/routes/      → hangi adres, hangi sayfa   │
│ app/forms/       → form alanları + doğrulama  │
│ app/templates/   → HTML (Jinja2)              │
│ app/static/      → CSS, JS, görseller         │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ İŞ KATMANI                                    │
│ app/services/    → iş kuralları               │
│   (stok negatif olamaz, siparişi olan ürün    │
│    silinmez, kayıtta yalnızca müşteri/üretici)│
│ app/utils/       → rol dekoratörü, görsel     │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ VERİ KATMANI                                  │
│ app/repositories/ → sorgular (CRUD)           │
│ app/models/       → tablolar ve ilişkiler     │
└───────────────────────┬───────────────────────┘
                        ▼
                 SQLite (instance/app.db)
```

**Kural:** Her katman yalnızca bir alttakini çağırır. Rota doğrudan SQL yazmaz, servisi çağırır;
servis veri tabanına repository üzerinden ulaşır.

## 2. Neden katmanlı mimari?

- **Sorumluluk ayrımı:** Arayüzü değiştirmek iş kurallarını bozmaz; veri tabanını değiştirmek rotaları etkilemez.
- **Test kolaylığı:** İş kuralları servislerde olduğu için `tests/` içinde tek tek denenebilir.
- **Güvenlik:** Yetki ve doğrulama yalnızca arayüzde değil, sunucu tarafındaki servis/dekoratörde de yapılır.
- **Takım çalışması:** Herkes farklı katmanda/modülde çalışabilir.

Kaçınılan hata: "Her şeyi tek dosyada / tek katmanda toplamak" (ör. SQL'i doğrudan rota fonksiyonuna yazmak).

## 3. Klasör yapısının mantığı

| Klasör | Katman | Neden ayrı? |
|---|---|---|
| `app/routes/` | Sunum | Modül başına bir dosya (auth, producer, admin, main) |
| `app/forms/` | Sunum | Girdi doğrulaması tek yerde |
| `app/templates/` | Sunum | Rol başına alt klasör (producer, customer, admin) |
| `app/services/` | İş | İş kuralları arayüzden bağımsız |
| `app/repositories/` | Veri | Tekrarlanan sorgular tek yerde |
| `app/models/` | Veri | Tablo başına bir dosya |
| `tests/` | — | Otomatik testler (pytest) |
| `docs/` | — | ER diyagramı, mimari, güvenlik notu, modül açıklamaları |
| `migrations/`, `src/` | — | Hafta 4 Node.js + SQLite veri tabanı alıştırması |
| `instance/` | — | Yerel veri tabanı dosyası (git'e gönderilmez) |

## 4. Bir isteğin yolculuğu (örnek: üretici ürün ekler)

1. `POST /uretici/urunler/yeni` → `producer_routes.py` (`@role_required(PRODUCER)` rolü kontrol eder)
2. `ProductForm` alanları doğrular (zorunlu alanlar, stok ≥ 0, görsel uzantısı/boyutu)
3. `producer_service.create_product` iş kurallarını uygular (kategori var mı, birim geçerli mi, görsel gerçek mi)
4. `ProductRepository` kaydı ekler ve `commit` eder
5. Veri tabanı kısıtları (FK, NOT NULL, CHECK) son savunma hattıdır
6. Rota kullanıcıyı ürün listesine yönlendirir

## 5. Sözlü sınav: "Katmanlı mimariyi neden tercih ettin?"

Her katmanın tek bir görevi olsun diye. Arayüz, iş kuralları ve veri erişimi ayrı olunca bir yerdeki değişiklik
diğerini bozmuyor, kodu test etmek kolaylaşıyor ve güvenlik kontrolü sadece arayüze bırakılmıyor.
