# Hafta 4 — Veritabanı Tasarımı ve Veri Erişim Katmanı
**Proje:** Çiftçi Doğrudan Satış ve Fiyat Takip Platformu
**Teknoloji:** Node.js + SQLite (Node'un yerleşik `node:sqlite` modülü)

> **Neden bu teknoloji?** SQLite tek bir dosyadır (`ciftci.db`); sunucu kurmak, şifre ayarlamak gerekmez.
> Node.js 22.13+ sürümünde SQLite yerleşik geldiği için `npm install` ile **hiçbir paket kurulmaz**.
> C# + SQL Server'a göre kurulumu çok daha kolaydır, ama SQL bilgisi birebir aynıdır.

---

## 1. Visual Studio Code'da adım adım

1. **Node.js kur:** https://nodejs.org → **LTS** sürümünü indir (22.13 veya üstü olmalı).
   Kontrol: VS Code'da `Terminal > New Terminal` aç ve yaz:
   ```
   node --version
   ```
2. **Proje klasörünü aç:** Bu klasörü (`hafta4-veritabani`) masaüstüne çıkar →
   VS Code'da `File > Open Folder` ile aç.
3. **(Önerilen) Eklenti kur:** Sol menüdeki Extensions (Ctrl+Shift+X) → **"SQLite Viewer"** (Florian Klampfer).
   Bununla `ciftci.db` dosyasına tıklayıp tabloları görebilirsin.
4. **Tabloları oluştur (migration):**
   ```
   npm run migrate
   ```
5. **Sentetik veriyle doldur:**
   ```
   npm run seed
   ```
6. **CRUD + kısıt + transaction demosunu çalıştır:**
   ```
   npm run demo
   ```
7. **Her şeyi sıfırdan tek komutla** (hocaya gösterirken en pratiği):
   ```
   npm run hepsi
   ```

### Klasör yapısı
```
hafta4-veritabani/
├── migrations/
│   ├── 001_tablolari_olustur.sql   ← DDL: tablolar, ilişkiler, kısıtlar
│   └── 002_indeksler.sql           ← DDL: indeksler (+ neden eklenmediği açıklamaları)
├── src/
│   ├── db.js              ← Bağlantı + PRAGMA foreign_keys + transaction yardımcısı
│   ├── migrate.js         ← Migration aracı
│   ├── seed.js            ← KVKK uyumlu sentetik veri
│   ├── urunRepository.js  ← VERİ ERİŞİM KATMANI (CRUD)
│   ├── demo.js            ← Testler / gösterim
│   └── sifirla.js         ← Veritabanını siler
├── package.json
└── README.md
```

---

## 2. ER Modeli (Varlık-İlişki Diyagramı)

```
 ┌────────────────────┐ 1          0..1 ┌────────────────────┐
 │     KULLANICI      │─────────────────│      URETICI       │
 ├────────────────────┤                 ├────────────────────┤
 │ PK id              │                 │ PK id              │
 │    kullanici_adi U │                 │ FK kullanici_id  U │
 │    eposta        U │                 │    ciftlik_adi     │
 │    rol (CHECK)     │                 │    il              │
 │    olusturma_tar.  │                 └─────────┬──────────┘
 └─────────┬──────────┘                           │ 1
           │ 1                                    │
           │                                      │ N
           │ N                          ┌─────────┴──────────┐  1       N ┌────────────────────┐
 ┌─────────┴──────────┐                 │        URUN        │────────────│   FIYAT_GECMISI    │
 │      SIPARIS       │                 ├────────────────────┤            ├────────────────────┤
 ├────────────────────┤                 │ PK id              │            │ PK id              │
 │ PK id              │                 │ FK uretici_id      │            │ FK urun_id         │
 │ FK alici_id        │                 │    ad              │            │    fiyat (>0)      │
 │    tarih           │                 │    birim (CHECK)   │            │    tarih           │
 │    durum (CHECK)   │                 │    fiyat (>0)      │            └────────────────────┘
 └─────────┬──────────┘                 │    stok  (>=0)     │
           │ 1                          │    aktif           │
           │                            └──┬─────────────┬───┘
           │ N                           1 │             │ 1
 ┌─────────┴──────────┐   N               │             │ N
 │   SIPARIS_KALEMI   │───────────────────┘   ┌─────────┴──────────┐   N      1 ┌────────────────────┐
 │    (ara tablo)     │                       │   URUN_KATEGORI    │────────────│      KATEGORI      │
 ├────────────────────┤                       │    (ara tablo)     │            ├────────────────────┤
 │ PK,FK siparis_id   │                       ├────────────────────┤            │ PK id              │
 │ PK,FK urun_id      │                       │ PK,FK urun_id      │            │    ad            U │
 │    miktar (>0)     │                       │ PK,FK kategori_id  │            │    aciklama        │
 │    birim_fiyat     │                       └────────────────────┘            └────────────────────┘
 └────────────────────┘
 PK = Birincil anahtar   FK = Yabancı anahtar   U = UNIQUE
```

**İlişkilerin özeti**

| İlişki | Tür | Nasıl kuruldu |
|---|---|---|
| Kullanıcı – Üretici | 1 – 0..1 | `uretici.kullanici_id` FK + **UNIQUE** |
| Üretici – Ürün | 1 – N | `urun.uretici_id` FK |
| Ürün – Fiyat Geçmişi | 1 – N | `fiyat_gecmisi.urun_id` FK |
| Kullanıcı (alıcı) – Sipariş | 1 – N | `siparis.alici_id` FK |
| **Ürün – Kategori** | **N – N** | Ara tablo `urun_kategori` |
| **Sipariş – Ürün** | **N – N** | Ek alanlı ara tablo `siparis_kalemi` (miktar, birim_fiyat) |

---

## 3. Elle yazılıp açıklanan ilişki ve kısıt (Ödev Madde 3)

**İlişki — `fk_uretici_kullanici`** (`001_tablolari_olustur.sql`):
```sql
CONSTRAINT fk_uretici_kullanici
    FOREIGN KEY (kullanici_id) REFERENCES kullanici(id)
    ON DELETE CASCADE
```
- `uretici.kullanici_id` değeri **mutlaka** `kullanici` tablosunda var olan bir `id` olmalı.
- `kullanici_id` aynı zamanda `UNIQUE` olduğu için bir kullanıcının **en fazla bir** üretici profili olur → 1-1 ilişki.
- `ON DELETE CASCADE`: kullanıcı hesabı silinirse üretici profili de otomatik silinir (profil, hesap olmadan anlamsız).

**Kısıt — `CHECK (fiyat > 0)`** (`urun` tablosu):
- Uygulamada bir hata olsa bile veritabanı 0 veya negatif fiyatı **kabul etmez**.
- Demoda `fiyat: -5` denendiğinde: `CHECK constraint failed: fiyat > 0`.

---

## 4. Teorik kavramlar (kısa)

### DDL ve DML
| | DDL (Data **Definition** Language) | DML (Data **Manipulation** Language) |
|---|---|---|
| Ne yapar | Tablonun **yapısını** tanımlar | Tablodaki **veriyi** işler |
| Komutlar | `CREATE`, `ALTER`, `DROP` | `INSERT`, `SELECT`, `UPDATE`, `DELETE` |
| Projede | `migrations/*.sql` | `urunRepository.js`, `seed.js` |

### İndeks
Kitabın arkasındaki dizin gibidir: aranan değerin hangi satırda olduğunu doğrudan bulur.
**Artısı:** `WHERE`, `JOIN`, `ORDER BY` hızlanır. **Eksisi:** disk alanı harcar, her `INSERT/UPDATE/DELETE`'te indeks de güncellendiği için yazma yavaşlar.
Bu yüzden sadece **sık sorgulanan ve çok farklı değer alan** sütunlara eklenir.

### Referans bütünlüğü (Referential Integrity)
Bir tablodaki yabancı anahtar değerinin, başvurduğu tabloda **gerçekten var olması** kuralı.
"Var olmayan üreticinin ürünü" veya "silinmiş ürüne ait sipariş kalemi" gibi **yetim (orphan) kayıtları** engeller.
Silme davranışları:
- `CASCADE` → ana kayıt silinince bağlı kayıtlar da silinir (ürün → fiyat geçmişi).
- `RESTRICT` → bağlı kayıt varsa ana kayıt **silinemez** (ürünü olan üretici).
- `SET NULL` → bağlı kayıttaki FK `NULL` yapılır (projede kullanılmadı).

> ⚠️ SQLite'ta FK kontrolü varsayılan olarak **kapalıdır**. `db.js` içindeki `PRAGMA foreign_keys = ON;` satırı bu yüzden zorunlu.

### İşlem (Transaction) — ACID
Birden fazla SQL komutunu **tek bir bütün** olarak çalıştırır: **ya hepsi ya hiçbiri**.
- `BEGIN` → başlat, `COMMIT` → kalıcı yap, `ROLLBACK` → hepsini geri al.
- **A**tomicity (bölünmezlik), **C**onsistency (tutarlılık), **I**solation (yalıtım), **D**urability (kalıcılık).
- Projede: `siparisOlustur()` sipariş başlığı + stok düşme + sipariş kalemi yazar. Stok yetmezse **hiçbiri** kalmaz (demo 6. adım).

---

## 5. Sözlü sınav soruları — hazır cevaplar

### 1) Bir tabloya neden indeks ekledin / eklemedin?
**Ekledim:** `urun.uretici_id` — "üreticinin ürünleri" en sık sorgu; ayrıca SQLite FK sütunlarına otomatik indeks koymaz, üretici silinirken RESTRICT kontrolü tüm tabloyu taramasın.
`fiyat_gecmisi(urun_id, tarih)` — bileşik indeks; fiyat takip ekranındaki `WHERE urun_id = ? ORDER BY tarih` sorgusunu tek indeksle karşılar.
**Eklemedim:** `urun.aktif`, `siparis.durum` — çok az farklı değer alır (düşük seçicilik), indeks fayda sağlamaz ama yazmayı yavaşlatır. `kullanici.eposta` — `UNIQUE` zaten otomatik indeks oluşturuyor.
**Kanıt** (`EXPLAIN QUERY PLAN` ile kontrol edildi):
```
SELECT * FROM urun WHERE uretici_id=1   → SEARCH urun USING INDEX idx_urun_uretici
SELECT * FROM urun WHERE aktif=1        → SCAN urun   (indeks yok, bilerek)
```

### 2) Yabancı anahtar kısıtı ne işe yarar?
İki tablo arasındaki ilişkiyi **veritabanı seviyesinde** garanti eder. Var olmayan bir kayda başvurmayı (`ureticiId: 999` → `FOREIGN KEY constraint failed`) ve bağlı kaydı olan ana kaydın yanlışlıkla silinmesini (`RESTRICT`) engeller. Uygulama kodunda hata olsa bile veri tutarlı kalır.

### 3) N-N ilişkiyi nasıl modelledin?
İki tablo arasında N-N ilişki doğrudan kurulamaz; **ara tablo** (junction table) kullandım.
`urun_kategori(urun_id, kategori_id)`: iki sütun da FK, ikisi birlikte **bileşik birincil anahtar** → aynı ürün aynı kategoriye iki kez eklenemez. Örn. "Süzme Bal" hem *Arı Ürünleri* hem *Kahvaltılık* kategorisinde.
İkinci örnek `siparis_kalemi`: ara tablo ilişkiye ait ek bilgi de tutar (`miktar`, `birim_fiyat`). `birim_fiyat` ayrıca saklanır çünkü ürün fiyatı sonradan değişse de eski siparişin tutarı değişmemeli.

### 4) Migration neden kullanılır?
Veritabanı şemasındaki değişiklikleri **sürüm kontrollü, sıralı ve tekrarlanabilir** dosyalar halinde tutmak için.
- Takımdaki herkes ve sunucu aynı şemaya `npm run migrate` ile ulaşır; elle SQL çalıştırmaya gerek kalmaz.
- `schema_migrations` tablosu hangi dosyanın uygulandığını kaydeder; ikinci çalıştırmada uygulanmışlar **atlanır**.
- Her migration bir transaction içinde: hata olursa yarım şema kalmaz.
- Değişiklik gerekirse eski dosya **düzenlenmez**, yeni dosya eklenir (ör. `003_urune_aciklama_ekle.sql` içinde `ALTER TABLE urun ADD COLUMN aciklama TEXT;`).

### 5) Bir CRUD işleminin SQL'ini açıkla (UPDATE örneği)
```sql
UPDATE urun
SET fiyat = COALESCE(:fiyat, fiyat),          -- yeni fiyat verildiyse onu, verilmediyse eskisini koru
    stok  = COALESCE(:stok, stok),
    guncelleme_tarihi = datetime('now')       -- değişiklik zamanını kaydet
WHERE id = :id                                -- SADECE bu ürünü güncelle (WHERE unutulursa TÜM tablo değişir!)
```
- `:fiyat`, `:id` **parametredir**; değer SQL metnine yapıştırılmaz → **SQL Injection** engellenir.
- `run()` sonucu `changes` değeri kaç satırın değiştiğini verir (0 ise ürün yok).
- Fiyat değiştiyse aynı transaction içinde `fiyat_gecmisi` tablosuna `INSERT` yapılır.
- `CHECK (fiyat > 0)` kısıtı negatif fiyata güncellemeyi engeller.

---

## 6. KVKK uyumu
- **Gerçek kişisel veri yok.** Kullanıcı adları `alici01`, `uretici03` gibi üretilmiş kodlar.
- E-postalar `@ornek.test`: `.test` uzantısı RFC 2606 ile test için ayrılmıştır, gerçek adres olamaz.
- **Veri minimizasyonu:** TC kimlik no, telefon, açık adres gibi alanlar şemaya hiç eklenmedi.
- Veriler sabit tohumlu rastgele üretilir; her çalıştırmada aynı sonuç çıkar.

## 7. Kaçınılan hatalar
| Hata | Bu projede ne yapıldı |
|---|---|
| İlişkisiz / denormalize tablolar | Üretici bilgisi ürün tablosunda tekrar edilmedi, `uretici_id` FK ile bağlandı. Kategoriler virgüllü metin değil, ara tabloda. |
| Kısıt tanımlamamak | PK, FK, UNIQUE, NOT NULL, CHECK hepsi kullanıldı; demo 8 kısıtın çalıştığını test ediyor. |
| Gerçek kişisel veri | Tamamen sentetik veri (bkz. Bölüm 6). |
